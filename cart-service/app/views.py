from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Cart, CartItem
from .serializers import CartSerializer, CartItemSerializer
import requests

# Link gọi các Service (book-service + clothes-service đã gộp vào product-service)
BOOK_SERVICE_URL = "http://product-service:8000"
CLOTHES_SERVICE_URL = "http://product-service:8000"

class CartCreate(APIView):
    def post(self, request):
        serializer = CartSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)

class AddCartItem(APIView):
    def post(self, request):
        book_id = request.data.get("book_id")
        item_type = request.data.get("item_type", "book")

        # ==========================================
        # SỬA TỪ GỐC: CÂN MỌI THỂ LOẠI DATA TỪ FRONTEND
        # Nếu Frontend gửi customer_id -> Lấy
        # Nếu Frontend gửi cart (code cũ) -> Chấp nhận luôn
        # Nếu Frontend KHÔNG GỬI GÌ CẢ -> Tự ép mặc định là khách hàng số 1     
        # ==========================================
        customer_id = request.data.get("customer_id") or request.data.get("cart") or 1

        add_qty = int(request.data.get("quantity", 1))

        # 1. Tự động tìm Giỏ hàng của khách này (hoặc tạo mới nếu chưa có)      
        cart, created = Cart.objects.get_or_create(customer_id=customer_id)     

        # 2. Gọi Service tương ứng để check sản phẩm thật hay giả
        try:
            if item_type == "cloth":
                r = requests.get(f"{CLOTHES_SERVICE_URL}/clothes/")
                items = r.json()
                if not any(str(b["id"]) == str(book_id) for b in items):
                    return Response({"error": "Quần áo không tồn tại trong kho!"}, status=400)
            else:
                r = requests.get(f"{BOOK_SERVICE_URL}/books/")
                items = r.json()
                if not any(str(b["id"]) == str(book_id) for b in items):
                    return Response({"error": "Sách không tồn tại trong kho!"}, status=400)
        except Exception:
            return Response({"error": f"Không kết nối được với {item_type} Service"}, status=500)

        # 3. LOGIC GỘP SÁCH SIÊU CHỐNG LỖI
        existing_item = CartItem.objects.filter(cart=cart, book_id=book_id, item_type=item_type).first()

        if existing_item:
            # Nếu đã có -> Cộng dồn số lượng
            existing_item.quantity += add_qty
            existing_item.save()
            serializer = CartItemSerializer(existing_item)
            return Response(serializer.data, status=200)
        else:
            # Nếu chưa có -> Tạo mới hoàn toàn
            data = request.data.copy()
            # Dọn dẹp key 'cart' cũ nếu có để tránh xung đột với Django
            if "cart" in data:
                del data["cart"]

            # Ép cứng ID giỏ hàng chuẩn xác vào data để lưu
            data["cart"] = cart.id

            serializer = CartItemSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=201)
            # In thẳng lỗi ra nếu vẫn tịt để debug
            print("Lỗi Serializer:", serializer.errors)
            return Response(serializer.errors, status=400)


class ViewCart(APIView):
    def get(self, request, customer_id):
        try:
            cart = Cart.objects.filter(customer_id=customer_id).first()
            if not cart:
                # Nếu lỡ chưa có giỏ nào thì tạo mới luôn cho khách
                cart = Cart.objects.create(customer_id=customer_id)
            items = CartItem.objects.filter(cart=cart)
            serializer = CartItemSerializer(items, many=True)
            return Response(serializer.data)
        except Cart.DoesNotExist:
            return Response({"error": "Không tìm thấy giỏ hàng của khách này"}, status=404)




class ManageCartItem(APIView):
    # API Sửa số lượng (Code lúc nãy)
    def put(self, request, item_id):
        try:
            item = CartItem.objects.get(id=item_id)
            new_quantity = request.data.get("quantity")
            if new_quantity is not None:
                item.quantity = int(new_quantity)
                item.save()
                return Response({"message": "Cập nhật số lượng thành công!", "new_quantity": item.quantity})
            return Response({"error": "Thiếu quantity"}, status=400)
        except CartItem.DoesNotExist:
            return Response({"error": "Không tìm thấy sách"}, status=404)

    # API Xóa sách (Chức năng ông vừa đề xuất)
    def delete(self, request, item_id):
        try:
            item = CartItem.objects.get(id=item_id)
            item.delete()
            return Response({"message": "Đã đá cuốn sách này ra khỏi giỏ!"})
        except CartItem.DoesNotExist:
            return Response({"error": "Sách không tồn tại trong giỏ"}, status=404)