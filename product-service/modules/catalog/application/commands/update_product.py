"""
Command: UpdateProduct
=======================
Chỉ chứa các field muốn cập nhật (partial update).
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class UpdateProductCommand:
    product_id: int
    name: Optional[str] = None
    price: Optional[Decimal] = None
    stock: Optional[int] = None
    category_id: Optional[int] = None
    image_url: Optional[str] = None
    attributes: Optional[dict] = None
