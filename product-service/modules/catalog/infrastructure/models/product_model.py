"""
Infrastructure Model: ProductModel
====================================
Django ORM model — nằm ở infrastructure, KHÔNG phải domain.
Domain entity (Product) và ORM model (ProductModel) tách biệt hoàn toàn.
"""
from django.db import models


class ProductModel(models.Model):
    """
    Bảng `products` gộp cả sách lẫn quần áo.

    attributes (JSONB) lưu thông tin đặc thù theo loại:
      - book:  {"author": "Tên tác giả", "isbn": "..."}
      - cloth: {"brand": "Gucci", "size": "M", "color": "White"}
    """
    PRODUCT_TYPES = [
        ('book',        'Sách'),
        ('cloth',       'Thời trang'),
        ('stationery',  'Văn phòng phẩm'),
        ('electronics', 'Điện tử'),
        ('toy',         'Đồ chơi'),
        ('cosmetic',    'Mỹ phẩm'),
        ('bag',         'Túi xách'),
        ('shoe',        'Giày dép'),
        ('watch',       'Đồng hồ'),
        ('gift',        'Quà tặng'),
    ]

    name         = models.CharField(max_length=255)
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPES, db_index=True)
    price        = models.DecimalField(max_digits=15, decimal_places=2)
    stock        = models.IntegerField(default=0)
    category_id  = models.IntegerField(null=True, blank=True, db_index=True)
    image_url    = models.URLField(max_length=1000, null=True, blank=True)
    attributes   = models.JSONField(default=dict)   # ← điểm cốt lõi DDD

    class Meta:
        app_label = 'infrastructure'
        db_table  = 'products'
        ordering  = ['id']

    def __str__(self):
        return f"[{self.product_type}] {self.name}"
