"""
Infrastructure: ProductRepositoryImpl
========================================
Triển khai ProductRepository bằng Django ORM.
Convert qua lại giữa ProductModel (ORM) ↔ Product (Domain Entity).
"""
from decimal import Decimal
from typing import List, Optional

from modules.catalog.domain.entities.product import Product
from modules.catalog.domain.repositories.product_repository import ProductRepository
from modules.catalog.infrastructure.models.product_model import ProductModel


def _to_entity(m: ProductModel) -> Product:
    """ORM model → Domain entity."""
    return Product(
        id=m.id,
        name=m.name,
        product_type=m.product_type,
        price=Decimal(str(m.price)),
        stock=m.stock,
        category_id=m.category_id,
        image_url=m.image_url,
        attributes=m.attributes or {},
    )


def _to_model_fields(p: Product) -> dict:
    """Domain entity → dict fields cho ORM."""
    return {
        "name":         p.name,
        "product_type": p.product_type,
        "price":        p.price,
        "stock":        p.stock,
        "category_id":  p.category_id,
        "image_url":    p.image_url,
        "attributes":   p.attributes,
    }


class ProductRepositoryImpl(ProductRepository):

    def find_all(
        self,
        product_type: Optional[str] = None,
        category_id: Optional[int] = None,
    ) -> List[Product]:
        qs = ProductModel.objects.all()
        if product_type:
            qs = qs.filter(product_type=product_type)
        if category_id:
            qs = qs.filter(category_id=category_id)
        return [_to_entity(m) for m in qs]

    def find_by_id(self, product_id: int) -> Optional[Product]:
        try:
            return _to_entity(ProductModel.objects.get(pk=product_id))
        except ProductModel.DoesNotExist:
            return None

    def save(self, product: Product) -> Product:
        fields = _to_model_fields(product)
        if product.id:
            ProductModel.objects.filter(pk=product.id).update(**fields)
            m = ProductModel.objects.get(pk=product.id)
        else:
            m = ProductModel.objects.create(**fields)
        return _to_entity(m)

    def delete(self, product_id: int) -> bool:
        deleted, _ = ProductModel.objects.filter(pk=product_id).delete()
        return deleted > 0
