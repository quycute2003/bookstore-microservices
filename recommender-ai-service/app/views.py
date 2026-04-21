from rest_framework.views import APIView
from rest_framework.response import Response
from .models import AI_Log
from .serializers import AILogSerializer
import requests
from collections import defaultdict

BOOK_SERVICE_URL = "http://product-service:8000"
COMMENT_SERVICE_URL = "http://comment-rate-service:8000"

class GetRecommendations(APIView):
    def post(self, request):
        customer_id = request.data.get("customer_id")
        
        try:
            review_res = requests.get(f"{COMMENT_SERVICE_URL}/reviews/")
            reviews = review_res.json() if review_res.status_code == 200 else []

            book_res = requests.get(f"{BOOK_SERVICE_URL}/books/")
            books = book_res.json() if book_res.status_code == 200 else []
        except Exception:
            return Response({"error": "AI đứt cáp, mất kết nối hệ thống!"}, status=500)

        if not books:
            return Response({"message": "Kho hết sách, AI xin từ chối tư vấn!"})

        # --- THUẬT TOÁN V3: PHÂN TÍCH TOÀN BỘ HỒ SƠ KHÁCH HÀNG ---
        user_reviews = [r for r in reviews if str(r['customer_id']) == str(customer_id)]
        
        # Danh sách sách đã đọc (để lát nữa không gợi ý lại)
        read_book_ids = [str(r['book_id']) for r in user_reviews]
        
        # 1. Lọc ra những cuốn khách khen (từ 4 sao trở lên)
        good_reviews = [r for r in user_reviews if int(r['rating']) >= 4]
        
        preferred_category_id = None
        if good_reviews:
            # 2. Gom nhóm: Đếm xem khách khen Thể loại nào nhiều nhất
            category_counts = defaultdict(int)
            for r in good_reviews:
                for b in books:
                    if str(b['id']) == str(r['book_id']):
                        cat_id = b.get('category_id')
                        if cat_id:
                            category_counts[cat_id] += 1
                        break
            
            if category_counts:
                # 3. Chốt sổ: Thể loại có lượt khen nhiều nhất chính là "Gu"
                preferred_category_id = max(category_counts, key=category_counts.get)

        # 4. Lọc danh sách đề cử (Cấm tuyệt đối gạ mua lại sách đã đọc)
        unread_books = [b for b in books if str(b['id']) not in read_book_ids]
        candidate_books = unread_books
        reason_prefix = "Khám phá ngẫu nhiên: "
        
        if preferred_category_id:
            same_cat_books = [b for b in unread_books if b.get('category_id') == preferred_category_id]
            if same_cat_books: # Nếu có sách cùng thể loại thì mới ưu tiên
                candidate_books = same_cat_books
                reason_prefix = "Dựa trên thể loại bạn yêu thích: "
            
        if not candidate_books:
            # Ưu tiên 2 (Mở rộng): Lấy sách CHƯA ĐỌC bất kỳ nếu kho hết sách đúng Gu
            candidate_books = [b for b in books if str(b['id']) not in read_book_ids]
            reason_prefix = "Có thể bạn sẽ thích: "

        # 5. Tìm cuốn Đỉnh nhất trong nhóm đề cử (Collaborative Filtering)
        book_scores = defaultdict(list)
        for r in reviews:
            book_scores[r['book_id']].append(r['rating'])
        
        avg_scores = {b_id: sum(scores)/len(scores) for b_id, scores in book_scores.items()}
        candidate_ids = [b['id'] for b in candidate_books]
        
        # Chỉ lấy điểm của những ứng viên hợp lệ
        valid_scores = {b_id: score for b_id, score in avg_scores.items() if b_id in candidate_ids}

        recommended_book = None
        reason = ""

        if valid_scores:
            # Bốc cuốn có điểm trung bình cao nhất
            best_book_id = max(valid_scores, key=valid_scores.get)
            best_score = valid_scores[best_book_id]
            for b in candidate_books:
                if b['id'] == best_book_id:
                    recommended_book = b
                    reason = f"{reason_prefix}Cuốn này đang Top Trending với {best_score:.1f}/5.0 sao!"
                    break

        # Fallback cuối cùng: Nếu chưa có điểm đánh giá, bốc cuốn tồn kho nhiều nhất
        if not recommended_book:
            if candidate_books:
                recommended_book = max(candidate_books, key=lambda x: x['stock'])
                reason = f"{reason_prefix}Sách mới đang bán cực chạy, xả kho giá hời!"
            else:
                return Response({"message": "Khách hàng này đã đọc sạch kho sách rồi, vô phương cứu chữa!"})

        # Lưu vào não bộ AI
        AI_Log.objects.create(
            customer_id=customer_id,
            recommended_book_id=recommended_book['id'],
            reason=reason
        )

        return Response({
            "message": f"🤖 Đã quét xong hồ sơ đa sở thích của khách {customer_id}:",
            "book": recommended_book,
            "reason": reason
        })