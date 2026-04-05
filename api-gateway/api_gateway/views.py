from django.shortcuts import render
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
# ==========================================
# KHU VỰC 1: CUSTOMER (KHÁCH HÀNG)
# ==========================================

# 1. Khám sức khỏe (Health Check)
def health_check(request):
    return JsonResponse({
        "status": "ok",
        "service": "api-gateway",
        "message": "Gateway is running smoothly!"
    }, status=200)

# 2. Đăng ký / Đăng nhập
def auth_view(request):
    return render(request, 'login.html')

# 3. Trang chủ (Book List & AI)
import random

def home(request):
    # 1. Gọi Book Service lấy kho sách
    try:
        res = requests.get("http://book-service:8000/books/")
        books = res.json() if res.status_code == 200 else []
        
        # 🔥 THÊM ĐOẠN NÀY: Gắn tiền tố cho toàn bộ sách để Frontend render link chuẩn
        for b in books:
            b['type'] = 'book'
            b['product_id'] = f"book_{b['id']}"
            
    except Exception:
        books = []

    # 2. Gọi Catalog Service lấy danh mục đầy đủ (có tên)
    try:
        cat_res = requests.get("http://catalog-service:8000/categories/")
        categories = cat_res.json() if cat_res.status_code == 200 else []
    except Exception:
        # Fallback: trích category_id từ sách nếu catalog-service sập
        cat_ids = list(set([b.get('category_id') for b in books if b.get('category_id')]))
        categories = [{'id': c, 'name': f'Danh mục #{c}'} for c in cat_ids]

    # 3. Gọi AI Service lấy gợi ý sách
    ai_book = None
    ai_reason = "Gợi ý hôm nay dành riêng cho bạn!"
    try:
        ai_res = requests.post("http://recommender-ai-service:8000/ai-suggest/", json={"customer_id": 1}, timeout=3)
        if ai_res.status_code == 200:
            ai_data = ai_res.json()
            if ai_data.get("book"):
                ai_book = ai_data["book"]
                
                # 🔥 THÊM ĐOẠN NÀY: Đảm bảo cuốn sách AI gợi ý cũng có đúng cấu trúc ID
                ai_book['type'] = 'book'
                ai_book['product_id'] = f"book_{ai_book['id']}"
                ai_reason = ai_data.get("reason", ai_reason)
    except Exception:
        pass

    # 4. Tạo list gợi ý 4 sách
    ai_books = []
    if ai_book:
        ai_books.append(ai_book)
        same_cat_books = [b for b in books if b.get('category_id') == ai_book.get('category_id') and b['id'] != ai_book['id']]
        random.shuffle(same_cat_books)
        ai_books.extend(same_cat_books[:3])
    if len(ai_books) < 4 and books:
        other_books = [b for b in books if b not in ai_books]
        random.shuffle(other_books)
        ai_books.extend(other_books[:(4 - len(ai_books))])

    # 5. Tính khoảng giá để frontend biết mà lọc
    prices = [float(b.get('price', 0)) for b in books if b.get('price')]
    max_price = int(max(prices)) + 1 if prices else 500

    return render(request, 'index.html', {
        'books': books,
        'categories': categories,
        'ai_books': ai_books,
        'ai_reason': ai_reason,
        'max_price': max_price,
    })
# 3. Trang Chi tiết Sản phẩm & Review
def product_detail(request, product_id):
    product = None
    product_type = None
    real_id = product_id

    # Parse prefix: book_1 → type='book', id='1' | cloth_3 → type='cloth', id='3'
    if product_id.startswith('book_'):
        product_type = 'book'
        real_id = product_id.replace('book_', '')
    elif product_id.startswith('cloth_'):
        product_type = 'cloth'
        real_id = product_id.replace('cloth_', '')

    # Tìm trong Books
    if product_type in (None, 'book'):
        try:
            book_res = requests.get(f"http://book-service:8000/books/{real_id}/")
            if book_res.status_code == 200:
                product = book_res.json()
                product['type'] = 'book'
                try:
                    cat_res = requests.get(f"http://catalog-service:8000/categories/{product.get('category_id')}/")
                    if cat_res.status_code == 200:
                        product['category_name'] = cat_res.json().get('name')
                except:
                    pass
        except: pass

    # Tìm trong Clothes
    if not product and product_type in (None, 'cloth'):
        try:
            cloth_res = requests.get(f"http://clothes-service:8000/clothes/{real_id}/")
            if cloth_res.status_code == 200:
                product = cloth_res.json()
                product['type'] = 'cloth'
                product['title'] = product.get('name')
                product['author'] = product.get('brand')
        except: pass

    # Lấy Reviews
    try:
        cmt_res = requests.get("http://comment-rate-service:8000/reviews/")
        all_reviews = cmt_res.json() if cmt_res.status_code == 200 else []
        reviews = [r for r in all_reviews if str(r.get('book_id', '')) == str(real_id)]
    except Exception:
        reviews = []

    return render(request, 'detail.html', {'product': product, 'reviews': reviews})

# Trang danh sách sản phẩm
def listing_view(request):
    products = []
    brands = set()
    categories = []

    # Danh mục sách
    try:
        cat_res = requests.get("http://catalog-service:8000/categories/")
        if cat_res.status_code == 200:
            categories = cat_res.json()
    except Exception: pass
    
    cat_dict = {str(c['id']): c['name'] for c in categories}

    # Fetch books
    try:
        book_res = requests.get("http://book-service:8000/books/")
        if book_res.status_code == 200:
            books = book_res.json()
            for b in books:
                b['type'] = 'book'
                b['product_id'] = f"book_{b['id']}"
                b['category_name'] = cat_dict.get(str(b.get('category_id')), "Sách Khảo Cứu")
                products.append(b)
    except: pass

    # Fetch clothes
    try:
        cloth_res = requests.get("http://clothes-service:8000/clothes/")
        if cloth_res.status_code == 200:
            clothes = cloth_res.json()
            for c in clothes:
                c['type'] = 'cloth'
                c['product_id'] = f"cloth_{c['id']}"
                c['title'] = c.get('name')
                brand = c.get('brand', 'Khác')
                c['category_name'] = brand
                brands.add(brand)
                products.append(c)
    except: pass
    
    # Shuffle the products slightly for a mixed look
    import random
    random.shuffle(products)

    context = {
        'products_json': json.dumps(products),
        'categories': categories,
        'brands': list(brands)
    }
    return render(request, 'listing.html', context)

# 4. Trang Giỏ hàng
# 4. Trang Giỏ hàng
def cart_view(request):
    # 1. GỌI ĐÚNG CỬA: Gọi sang hàm ViewCart của Cart Service (Truyền customer_id = 1)
    try:
        cart_res = requests.get("http://cart-service:8000/carts/1/")
        if cart_res.status_code == 200:
            my_cart_items = cart_res.json()
        else:
            print(f"Lỗi GET Cart: {cart_res.status_code} - {cart_res.text}")
            my_cart_items = []
    except Exception as e:
        print("Lỗi đứt cáp Cart Service:", e)
        my_cart_items = []

    # 2. Gọi Book/Clothes Service để lấy Tên và Ảnh
    try:
        book_res = requests.get("http://book-service:8000/books/")
        books = book_res.json() if book_res.status_code == 200 else []
        book_dict = {str(b['id']): b for b in books}
    except Exception:
        book_dict = {}

    try:
        clothes_res = requests.get("http://clothes-service:8000/clothes/")
        clothes = clothes_res.json() if clothes_res.status_code == 200 else []
        clothes_dict = {str(c['id']): c for c in clothes}
    except Exception:
        clothes_dict = {}

    # 3. Phép thuật Mix & Match
    display_items = []
    total_price = 0

    for item in my_cart_items:
        b_id = str(item.get('book_id', item.get('book', '')))
        item_type = item.get('item_type', 'book')
        b_info = None

        if item_type == 'cloth':
            b_info = clothes_dict.get(b_id)
        else:
            b_info = book_dict.get(b_id)

        if b_info:
            qty = int(item.get('quantity', 1))
            price = float(b_info.get('price', 0))
            subtotal = qty * price
            total_price += subtotal

            # Lấy Title (Book) hoặc Name (Cloth)
            title = b_info.get('title')
            if not title:
                title = b_info.get('name', 'Sản phẩm')

            display_items.append({
                'item_id': item.get('id'),
                'book_id': b_id,
                'item_type': item_type,
                'title': title,
                'image_url': b_info.get('image_url'),
                'price': price,
                'quantity': qty,
                'subtotal': round(subtotal, 2)
            })

    return render(request, 'cart.html', {
        'cart_items': display_items,
        'total_price': round(total_price, 2)
    })

# 5. Trang Chốt đơn
def checkout_view(request):
    return render(request, 'checkout.html')

# 6. Lịch sử Đơn hàng
def orders_view(request):
    return render(request, 'orders.html')


# ==========================================
# KHU VỰC 2: BACK-OFFICE (BAN QUẢN TRỊ)
# ==========================================

# 7. Quản lý kho (Staff)
def staff_dashboard(request):
    return render(request, 'staff_dashboard.html')

# 8. Báo cáo doanh thu (Manager)
def manager_dashboard(request):
    # Lấy toàn bộ đơn hàng từ order-service
    try:
        res = requests.get("http://order-service:8000/orders/")
        orders = res.json() if res.status_code == 200 else []
    except Exception:
        orders = []

    # ---- KPI Calculations ----
    total_revenue   = sum(float(o.get('total_price', 0)) for o in orders)
    total_orders    = len(orders)
    pending_orders  = sum(1 for o in orders if o.get('status') == 'PENDING')
    approved_orders = sum(1 for o in orders if o.get('status') == 'APPROVED')
    shipping_orders = sum(1 for o in orders if o.get('status') == 'PAID_AND_SHIPPING')
    delivered_orders= sum(1 for o in orders if o.get('status') == 'DELIVERED')
    cancelled_orders= sum(1 for o in orders if o.get('status') == 'CANCELLED')

    # 10 đơn gần nhất (order-service trả về ASC → reverse để mới nhất lên đầu)
    recent_orders = list(reversed(orders))[:10]

    return render(request, 'manager_dashboard.html', {
        'total_revenue':    round(total_revenue, 2),
        'total_orders':     total_orders,
        'pending_orders':   pending_orders,
        'approved_orders':  approved_orders,
        'shipping_orders':  shipping_orders,
        'delivered_orders': delivered_orders,
        'cancelled_orders': cancelled_orders,
        'recent_orders':    recent_orders,
    })


# ==========================================
# KHU VỰC 3: API PROXY (Lách luật CORS)
# ==========================================
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import requests

# ==========================================
# CỖ MÁY PROXY VẠN NĂNG (DỨT ĐIỂM CORS 1 LẦN VÀ MÃI MÃI)
# ==========================================
@csrf_exempt
def universal_proxy(request, service_name, path):
    directory = {
        'cart': 'http://cart-service:8000',
        'book': 'http://book-service:8000',
        'clothes': 'http://clothes-service:8000',
        'order': 'http://order-service:8000',
        'pay': 'http://pay-service:8000',
        'ship': 'http://ship-service:8000',
        'ai': 'http://recommender-ai-service:8000',
        'catalog': 'http://catalog-service:8000',
        'comment': 'http://comment-rate-service:8000',
        'auth': 'http://auth-service:8000',
    }

    # 2. Kiểm tra xem Frontend có gọi đúng nhà không
    if service_name not in directory:
        return JsonResponse({"error": "Service không tồn tại trong danh bạ Gateway!"}, status=404)

    # 3. Lắp ráp địa chỉ thực tế
    if service_name == 'auth':
        target_url = f"{directory[service_name]}/api/auth/{path}"
    else:
        # Đường hầm cổ điển: Các service cũ nội bộ chỉ khai báo /carts/, /books/ chứ không có /api/
        target_url = f"{directory[service_name]}/{path}"

    # Đặt Radar để soi
    print(f"🔥 [GATEWAY PROXY] Đang chuyển hướng tới: {target_url}")

    # Forward headers (bỏ qua Host và Content-Length rác để tránh lỗi treo mạng)
    headers = {key: value for key, value in request.headers.items() if key.lower() not in ['host', 'content-length']}
    if hasattr(request, 'user_id'):
        headers['X-User-Id'] = str(request.user_id)
    if hasattr(request, 'user_role'):
        headers['X-User-Role'] = request.user_role

    try:
        if request.method == 'GET':
            res = requests.get(target_url, headers=headers, params=request.GET)
        elif request.method == 'POST':
            payload = json.loads(request.body) if request.body else {}
            res = requests.post(target_url, headers=headers, json=payload)
        elif request.method == 'PUT':
            payload = json.loads(request.body) if request.body else {}
            res = requests.put(target_url, headers=headers, json=payload)
        elif request.method == 'DELETE':
            res = requests.delete(target_url, headers=headers)
        else:
            return JsonResponse({"error": "Method không hỗ trợ"}, status=405)

        return HttpResponse(
            res.content, 
            status=res.status_code, 
            content_type=res.headers.get('Content-Type', 'application/json')
        )
    except Exception as e:
        print(f"Lỗi Proxy vạn năng: {e}")
        return JsonResponse({"error": "Sập cáp mạng nội bộ!"}, status=500)


def checkout_view(request):
    # 1. Gom Giỏ hàng & Tính tiền (Y hệt hàm cart_view)
    my_cart_items = []
    try:
        cart_res = requests.get("http://cart-service:8000/carts/1/")
        if cart_res.status_code == 200: my_cart_items = cart_res.json()
    except: pass

    try:
        book_res = requests.get("http://book-service:8000/books/")
        books = book_res.json() if book_res.status_code == 200 else []
        book_dict = {str(b['id']): b for b in books}
    except: book_dict = {}

    display_items = []
    total_price = 0
    for item in my_cart_items:
        b_info = book_dict.get(str(item.get('book_id')))
        if b_info:
            subtotal = int(item.get('quantity', 1)) * float(b_info.get('price', 0))
            total_price += subtotal
            display_items.append({'title': b_info.get('title'), 'quantity': item.get('quantity', 1), 'subtotal': round(subtotal, 2)})

    # 2. Lấy danh sách Phương thức Vận chuyển từ ship-service
    shipping_methods = []
    try:
        ship_res = requests.get("http://ship-service:8000/shipping-methods/")
        if ship_res.status_code == 200: shipping_methods = ship_res.json()
    except: pass

    # 3. Lấy danh sách Phương thức Thanh toán từ pay-service
    payment_methods = []
    try:
        pay_res = requests.get("http://pay-service:8000/payment-methods/")
        if pay_res.status_code == 200: payment_methods = pay_res.json()
    except: pass

    # 4. Trả hết ra Giao diện
    return render(request, 'checkout.html', {
        'cart_items': display_items,
        'total_price': round(total_price, 2),
        'shipping_methods': shipping_methods,
        'payment_methods': payment_methods
    })


def orders_view(request):
    try:
        # Gọi thẳng sang hàm GET của Order Service mà anh em mình viết ban nãy
        res = requests.get("http://order-service:8000/orders/")
        if res.status_code == 200:
            orders = res.json()
            # Đảo ngược list để đơn hàng mới nhất hiện lên đầu
            orders.reverse() 
        else:
            orders = []
    except Exception as e:
        print("Lỗi đứt cáp Order Service:", e)
        orders = []

    return render(request, 'orders.html', {'orders': orders})

def login_view(request):
    # Chỉ đơn giản là ném giao diện Login ra cho người dùng
    return render(request, 'login.html')

def staff_dashboard(request):
    # 1. Gom danh sách Đơn hàng từ nhà Order
    try:
        order_res = requests.get("http://order-service:8000/orders/")
        orders = order_res.json() if order_res.status_code == 200 else []
        orders.reverse() # Đảo ngược cho đơn mới lên đầu
    except Exception as e:
        print("Lỗi Order Service:", e)
        orders = []

    # 2. Gom danh sách Kho sách từ nhà Book
    try:
        book_res = requests.get("http://book-service:8000/books/")
        books = book_res.json() if book_res.status_code == 200 else []
        books.reverse()
    except Exception as e:
        print("Lỗi Book Service:", e)
        books = []

    # Gom danh sách Quần áo từ nhà Clothes
    try:
        clothes_res = requests.get("http://clothes-service:8000/clothes/")
        clothes = clothes_res.json() if clothes_res.status_code == 200 else []
        clothes.reverse()
    except Exception as e:
        print("Lỗi Clothes Service:", e)
        clothes = []

    # 3. Gom danh sách Danh mục từ Catalog Service
    try:
        cat_res = requests.get("http://catalog-service:8000/categories/")
        categories = cat_res.json() if cat_res.status_code == 200 else []
    except Exception as e:
        print("Lỗi Catalog Service:", e)
        categories = []

    # 4. Ném toàn bộ Data ra cho cái file HTML nó hiển thị
    return render(request, 'staff_dashboard.html', {
        'orders': orders, 
        'books': books, 
        'clothes': clothes, 
        'categories': categories
    })