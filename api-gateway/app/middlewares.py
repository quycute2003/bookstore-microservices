from django.http import JsonResponse
import jwt
from django.conf import settings
import redis
import time
import logging

logger = logging.getLogger(__name__)

# Kết nối tới Redis cache
redis_client = redis.StrictRedis(host='redis', port=6379, db=0, decode_responses=True)

class JWTAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.public_paths = [
            '/api/auth/login/',
            '/api/auth/register/',
            '/api/book/',
            '/api/clothes/',
            '/api/product/',
            '/login/',
            '/auth/',
            '/listing/',
            '/product/',
            '/health/',
            '/api/schema/',
            '/api/docs/',
            '/api/redoc/',
            '/admin/',
            '/',  # Trang chủ hoặc public
        ]

    def __call__(self, request):
        path = request.path
        
        # Check if the path is public or matches / (exact match)
        is_public = path == '/' or any(path.startswith(p) and p != '/' for p in self.public_paths)
        
        if not is_public:
            # Nếu là route /api/...
            if path.startswith('/api/'):
                auth_header = request.headers.get('Authorization')
                token = None
                
                if auth_header and auth_header.startswith('Bearer '):
                    token = auth_header.split(' ')[1]
                elif request.COOKIES.get('access_token'):
                    token = request.COOKIES.get('access_token')

                if not token:
                    return JsonResponse({"error": "Unauthorized. Token missing."}, status=401)
                
                try:
                    payload = jwt.decode(token, settings.AUTH_SERVICE_SECRET_KEY, algorithms=["HS256"])
                    request.user_id = payload.get('user_id')
                    request.user_role = payload.get('role')
                except jwt.ExpiredSignatureError:
                    return JsonResponse({"error": "Unauthorized. Token expired."}, status=401)
                except jwt.InvalidTokenError:
                    return JsonResponse({"error": "Unauthorized. Invalid token."}, status=401)
            
            # --- KIỂM TRA QUYỀN TRUY CẬP TRANG QUẢN TRỊ (HTML VIEWS) ---
            elif path.startswith('/staff/') or path.startswith('/manager/'):
                from django.shortcuts import redirect
                auth_header = request.headers.get('Authorization') or request.COOKIES.get('access_token')
                
                if not auth_header:
                    return redirect('/login/?msg=forbidden')
                
                # Hàm lấy token từ Cookie hoặc Header
                token = auth_header.split(' ')[1] if auth_header.startswith('Bearer ') else auth_header
                
                try:
                    payload = jwt.decode(token, settings.AUTH_SERVICE_SECRET_KEY, algorithms=["HS256"])
                    role = payload.get('role')
                    
                    # Rà soát đúng tuyến đúng người
                    if path.startswith('/manager/') and role != 'manager':
                        return redirect('/login/?msg=only_manager')
                    if path.startswith('/staff/') and role not in ['manager', 'staff']:
                        return redirect('/login/?msg=staff_manager_only')
                        
                    request.user_id = payload.get('user_id')
                    request.user_role = role
                except Exception:
                    return redirect('/login/?msg=invalid_token')
            
            # --- KIỂM TRA QUYỀN TRUY CẬP TRANG KHÁCH HÀNG (Mua sắm) ---
            elif path.startswith('/cart') or path.startswith('/checkout') or path.startswith('/orders'):
                from django.shortcuts import redirect
                auth_header = request.headers.get('Authorization') or request.COOKIES.get('access_token')
                
                if not auth_header:
                    return redirect('/auth/?next=' + path)
                
                token = auth_header.split(' ')[1] if auth_header.startswith('Bearer ') else auth_header
                
                try:
                    payload = jwt.decode(token, settings.AUTH_SERVICE_SECRET_KEY, algorithms=["HS256"])
                    request.user_id = payload.get('user_id')
                    request.user_role = payload.get('role')
                except Exception:
                    return redirect('/auth/?next=' + path)
                
        response = self.get_response(request)
        return response

class RateLimitMiddleware:
    """
    Giới hạn số lượng request từ một IP trong một khoảng thời gian (VD: 60 req / phút)
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.limit = 60  # Số request tối đa
        self.window = 60  # Trong vòng 60 giây

    def __call__(self, request):
        ip = self.get_client_ip(request)
        redis_key = f"rate_limit:{ip}"
        
        try:
            # Tăng biến đếm cho IP này
            req_count = redis_client.incr(redis_key)
            
            # Nếu là request đầu tiên, set thời gian hết hạn (window)
            if req_count == 1:
                redis_client.expire(redis_key, self.window)
                
            if req_count > self.limit:
                logger.warning(f"🚨 [RATE LIMIT] IP {ip} spamming. Blocked!")
                return JsonResponse({"error": "Too Many Requests. Vui lòng chậm lại!"}, status=429)
                
        except redis.ConnectionError:
            # Nếu Redis sập, bỏ qua rate limit để Gateway vẫn chạy được
            logger.error("Redis connection failed. Skipping Rate Limit.")

        response = self.get_response(request)
        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class RequestLoggingMiddleware:
    """
    Ghi log tập trung mọi request đi qua API Gateway
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        
        response = self.get_response(request)
        
        duration = round((time.time() - start_time) * 1000, 2)
        
        # Thông tin user nếu đã được JWTAuthMiddleware gỡ băng
        user_id = getattr(request, 'user_id', 'Anonymous')
        
        # IP Khách
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

        # Màu sắc cho Status Code
        status_code = response.status_code
        status_color = "\033[92m" if 200 <= status_code < 300 else "\033[93m" if 300 <= status_code < 400 else "\033[91m"
        reset_color = "\033[0m"

        log_data = f"🚀 [GATEWAY LOG] | {ip} | User: {user_id} | {request.method} {request.path} | {status_color}{status_code}{reset_color} | ⏱️ {duration}ms"
        
        # Print ra console để Docker log thu thập được
        print(log_data)
        
        return response
