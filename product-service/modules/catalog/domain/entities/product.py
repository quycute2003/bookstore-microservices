"""
Domain Entity: Product
======================
Core business object — không phụ thuộc bất kỳ framework nào.
Book và Clothes đều là Product, chỉ khác nhau ở attributes.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class Product:
    """
    Aggregate Root cho catalog.

    Attributes (JSONB) theo từng product_type:
      - book:  {"author": str, "isbn": str | None}
      - cloth: {"brand": str, "size": str, "color": str}
    """
    name: str
    product_type: str          # 'book' | 'cloth'
    price: Decimal
    stock: int
    attributes: dict = field(default_factory=dict)
    category_id: Optional[int] = None
    image_url: Optional[str] = None
    id: Optional[int] = None

    # ---- Business rules ----

    def is_in_stock(self) -> bool:
        return self.stock > 0

    def is_low_stock(self, threshold: int = 10) -> bool:
        return 0 < self.stock < threshold

    def reduce_stock(self, qty: int) -> None:
        if qty > self.stock:
            raise ValueError(f"Không đủ hàng: yêu cầu {qty}, còn {self.stock}")
        self.stock -= qty

    def increase_stock(self, qty: int) -> None:
        if qty <= 0:
            raise ValueError("Số lượng nhập kho phải > 0")
        self.stock += qty

    def update_price(self, new_price: Decimal) -> None:
        if new_price < 0:
            raise ValueError("Giá không thể âm")
        self.price = new_price

    # ---- Typed attribute helpers ----

    @property
    def author(self) -> Optional[str]:
        return self.attributes.get("author") if self.product_type == "book" else None

    @property
    def brand(self) -> Optional[str]:
        return self.attributes.get("brand") if self.product_type == "cloth" else None

    @property
    def size(self) -> Optional[str]:
        return self.attributes.get("size") if self.product_type == "cloth" else None

    @property
    def color(self) -> Optional[str]:
        return self.attributes.get("color") if self.product_type == "cloth" else None

    # Alias 'title' → name (backward compat với book-service cũ)
    @property
    def title(self) -> str:
        return self.name
