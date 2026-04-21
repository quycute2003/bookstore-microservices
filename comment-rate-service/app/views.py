from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Review
from .serializers import ReviewSerializer
import requests

BOOK_SERVICE_URL = "http://product-service:8000"

class SubmitReview(APIView):
    def post(self, request):
        customer_id = request.data.get("customer_id")
        book_id = request.data.get("book_id")
        rating = request.data.get("rating")
        
        if not all([customer_id, book_id, rating]):
            return Response({"error": "Thiếu customer_id, book_id hoặc rating!"}, status=400)
        
        # Cross-check: Xác minh xem kho có cuốn sách này không
        try:
            book_res = requests.get(f"{BOOK_SERVICE_URL}/books/")
            if book_res.status_code == 200:
                books = book_res.json()
                if not any(b['id'] == int(book_id) for b in books):
                    return Response({"error": "Sách không tồn tại, bạn đánh giá nhầm rồi!"}, status=404)
        except Exception:
            pass # Nếu book-service sập thì tạm bỏ qua check

        serializer = ReviewSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": f"Cảm ơn khách hàng {customer_id} đã đánh giá {rating} sao!",
                "review": serializer.data
            })
        return Response(serializer.errors, status=400)

    def get(self, request):
        reviews = Review.objects.all()
        serializer = ReviewSerializer(reviews, many=True)
        return Response(serializer.data)