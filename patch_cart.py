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
