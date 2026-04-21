"""
Command: CreateProduct
=======================
Data object mô tả ý định tạo sản phẩm mới.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class CreateProductCommand:
    name: str
    product_type: str          # 'book' | 'cloth'
    price: Decimal
    stock: int
    attributes: dict = field(default_factory=dict)
    category_id: Optional[int] = None
    image_url: Optional[str] = None
