from django.db import models

# Bảng lưu thông tin Đơn hàng
class Order(models.Model):
    customer_id = models.IntegerField()
    total_price = models.FloatField(default=0.0)
    # Thêm default=1 và default="N/A" vào 3 dòng này:
    shipping_method_id = models.IntegerField(default=1)
    payment_method_id = models.IntegerField(default=1)
    address = models.TextField(default="Chưa có địa chỉ")
    
    status = models.CharField(max_length=50, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
# Bảng lưu chi tiết từng cuốn sách khách mua
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    book_id = models.IntegerField()
    item_type = models.CharField(max_length=50, default='book')
    quantity = models.IntegerField()
    price = models.FloatField() # Phải lưu giá tiền tại thời điểm mua, lỡ sau này sách tăng giá!