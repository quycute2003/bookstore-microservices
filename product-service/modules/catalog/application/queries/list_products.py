"""
Query: ListProducts
====================
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ListProductsQuery:
    product_type: Optional[str] = None   # 'book' | 'cloth' | None (tất cả)
    category_id: Optional[int] = None
