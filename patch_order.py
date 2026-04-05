        # ==========================================
        # ��� VÁ LỖI Ở ĐÂY: PHẢI SANG BOOK SERVICE ĐỂ XEM GIÁ SÁCH/QUẦN ÁO
        # ==========================================
        try:
            books_res = requests.get(f"{BOOK_SERVICE_URL}/books/")
            books = {str(b['id']): b for b in books_res.json()}
        except:
            books = {}
            
        try:
            clothes_res = requests.get("http://clothes-service:8000/clothes/")
            clothes = {str(c['id']): c for c in clothes_res.json()}
        except:
            clothes = {}

        # 3. Tính tiền sách, Lưu chi tiết đơn và Xóa giỏ hàng
        for item in cart_items:
            book_id = str(item.get('book_id', ''))
            item_type = item.get('item_type', 'book')
            qty = int(item.get('quantity', 1))

            if item_type == 'cloth':
                b_info = clothes.get(book_id, {})
            else:
                b_info = books.get(book_id, {})
                
            price = float(b_info.get('price', 0))
            total_price += price * qty

            OrderItem.objects.create(
                order=order,
                book_id=int(book_id),
                item_type=item_type,
                quantity=qty,
                price=price
            )

            item_id = item.get('item_id') or item.get('id')
            try:
                requests.delete(f"{CART_SERVICE_URL}/cart-items/{item_id}/")
            except:
                pass
