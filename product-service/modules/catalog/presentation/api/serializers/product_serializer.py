"""
Serializers
============
Tách thành 2 serializer output cho backward-compatibility với api-gateway cũ:
  - BookOutputSerializer   → format y hệt book-service cũ
  - ClothOutputSerializer  → format y hệt clothes-service cũ
  - ProductInputSerializer → dùng chung cho POST/PUT
"""
from rest_framework import serializers


# ---- INPUT (tạo/sửa sản phẩm) ----

class BookInputSerializer(serializers.Serializer):
    title       = serializers.CharField()          # map → name
    author      = serializers.CharField()
    price       = serializers.DecimalField(max_digits=15, decimal_places=2)
    stock       = serializers.IntegerField(min_value=0)
    category_id = serializers.IntegerField(required=False, allow_null=True)
    image_url   = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    isbn        = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def to_command_data(self) -> dict:
        d = self.validated_data
        return {
            "name":         d["title"],
            "product_type": "book",
            "price":        d["price"],
            "stock":        d["stock"],
            "category_id":  d.get("category_id"),
            "image_url":    d.get("image_url"),
            "attributes":   {"author": d["author"], "isbn": d.get("isbn")},
        }


class ClothInputSerializer(serializers.Serializer):
    name        = serializers.CharField()
    brand       = serializers.CharField()
    size        = serializers.CharField()
    color       = serializers.CharField()
    price       = serializers.DecimalField(max_digits=15, decimal_places=2)
    stock       = serializers.IntegerField(min_value=0)
    category_id = serializers.IntegerField(required=False, allow_null=True)
    image_url   = serializers.URLField(required=False, allow_null=True, allow_blank=True)

    def to_command_data(self) -> dict:
        d = self.validated_data
        return {
            "name":         d["name"],
            "product_type": "cloth",
            "price":        d["price"],
            "stock":        d["stock"],
            "category_id":  d.get("category_id"),
            "image_url":    d.get("image_url"),
            "attributes":   {"brand": d["brand"], "size": d["size"], "color": d["color"]},
        }


# ---- OUTPUT (đọc sản phẩm) ----

class BookOutputSerializer(serializers.Serializer):
    """Trả về format giống book-service cũ để api-gateway không phải đổi."""
    id          = serializers.IntegerField()
    title       = serializers.CharField(source='name')
    author      = serializers.SerializerMethodField()
    price       = serializers.DecimalField(max_digits=15, decimal_places=2)
    stock       = serializers.IntegerField()
    category_id = serializers.IntegerField(allow_null=True)
    image_url   = serializers.URLField(allow_null=True)

    def get_author(self, obj) -> str:
        return obj.attributes.get("author", "") if isinstance(obj.attributes, dict) else ""


class ClothOutputSerializer(serializers.Serializer):
    """Trả về format giống clothes-service cũ để api-gateway không phải đổi."""
    id          = serializers.IntegerField()
    name        = serializers.CharField()
    brand       = serializers.SerializerMethodField()
    size        = serializers.SerializerMethodField()
    color       = serializers.SerializerMethodField()
    price       = serializers.DecimalField(max_digits=15, decimal_places=2)
    stock       = serializers.IntegerField()
    category_id = serializers.IntegerField(allow_null=True)
    image_url   = serializers.URLField(allow_null=True)

    def get_brand(self, obj) -> str:
        return obj.attributes.get("brand", "") if isinstance(obj.attributes, dict) else ""

    def get_size(self, obj) -> str:
        return obj.attributes.get("size", "") if isinstance(obj.attributes, dict) else ""

    def get_color(self, obj) -> str:
        return obj.attributes.get("color", "") if isinstance(obj.attributes, dict) else ""


class ProductOutputSerializer(serializers.Serializer):
    """Generic output — dùng cho endpoint /products/ (tất cả loại)."""
    id           = serializers.IntegerField()
    name         = serializers.CharField()
    product_type = serializers.CharField()
    price        = serializers.DecimalField(max_digits=15, decimal_places=2)
    stock        = serializers.IntegerField()
    category_id  = serializers.IntegerField(allow_null=True)
    image_url    = serializers.URLField(allow_null=True)
    attributes   = serializers.DictField()


class GenericProductInputSerializer(serializers.Serializer):
    """Input chung cho 8 loại sản phẩm mới — nhận attributes là dict tự do."""
    name        = serializers.CharField()
    price       = serializers.DecimalField(max_digits=15, decimal_places=2)
    stock       = serializers.IntegerField(min_value=0)
    category_id = serializers.IntegerField(required=False, allow_null=True)
    image_url   = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    attributes  = serializers.DictField(required=False, default=dict)

    def to_command_data(self, product_type: str) -> dict:
        d = self.validated_data
        return {
            "name":         d["name"],
            "product_type": product_type,
            "price":        d["price"],
            "stock":        d["stock"],
            "category_id":  d.get("category_id"),
            "image_url":    d.get("image_url"),
            "attributes":   d.get("attributes", {}),
        }
