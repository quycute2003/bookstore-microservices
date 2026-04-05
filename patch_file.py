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
