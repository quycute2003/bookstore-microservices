"""
Repository Interface (Abstract)
================================
Domain chỉ biết interface này, không biết gì về Django ORM hay database.
Implementation nằm ở infrastructure layer.
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from modules.catalog.domain.entities.product import Product


class ProductRepository(ABC):

    @abstractmethod
    def find_all(
        self,
        product_type: Optional[str] = None,
        category_id: Optional[int] = None,
    ) -> List[Product]:
        ...

    @abstractmethod
    def find_by_id(self, product_id: int) -> Optional[Product]:
        ...

    @abstractmethod
    def save(self, product: Product) -> Product:
        """Insert nếu chưa có id, update nếu đã có."""
        ...

    @abstractmethod
    def delete(self, product_id: int) -> bool:
        """Trả về True nếu xóa thành công, False nếu không tìm thấy."""
        ...
