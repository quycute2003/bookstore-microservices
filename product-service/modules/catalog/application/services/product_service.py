"""
Application Service: ProductService
=====================================
Xử lý use-case. Điều phối giữa Domain và Infrastructure.
Không chứa business rule — business rule nằm trong Entity.
"""
from decimal import Decimal
from typing import List, Optional

from modules.catalog.domain.entities.product import Product
from modules.catalog.domain.repositories.product_repository import ProductRepository
from modules.catalog.application.commands.create_product import CreateProductCommand
from modules.catalog.application.commands.update_product import UpdateProductCommand
from modules.catalog.application.queries.list_products import ListProductsQuery
from modules.catalog.application.queries.get_product import GetProductQuery


class ProductNotFound(Exception):
    pass


class ProductService:

    def __init__(self, repository: ProductRepository):
        self._repo = repository

    # ---- Queries ----

    def list_products(self, query: ListProductsQuery) -> List[Product]:
        return self._repo.find_all(
            product_type=query.product_type,
            category_id=query.category_id,
        )

    def get_product(self, query: GetProductQuery) -> Product:
        product = self._repo.find_by_id(query.product_id)
        if not product:
            raise ProductNotFound(f"Sản phẩm #{query.product_id} không tồn tại")
        return product

    # ---- Commands ----

    def create_product(self, cmd: CreateProductCommand) -> Product:
        if cmd.product_type not in ("book", "cloth"):
            raise ValueError(f"product_type không hợp lệ: {cmd.product_type}")
        if cmd.price < 0:
            raise ValueError("Giá không thể âm")
        if cmd.stock < 0:
            raise ValueError("Tồn kho không thể âm")

        product = Product(
            name=cmd.name,
            product_type=cmd.product_type,
            price=Decimal(str(cmd.price)),
            stock=cmd.stock,
            attributes=cmd.attributes or {},
            category_id=cmd.category_id,
            image_url=cmd.image_url,
        )
        return self._repo.save(product)

    def update_product(self, cmd: UpdateProductCommand) -> Product:
        product = self._repo.find_by_id(cmd.product_id)
        if not product:
            raise ProductNotFound(f"Sản phẩm #{cmd.product_id} không tồn tại")

        if cmd.name is not None:
            product.name = cmd.name
        if cmd.price is not None:
            product.update_price(Decimal(str(cmd.price)))
        if cmd.stock is not None:
            product.stock = cmd.stock
        if cmd.category_id is not None:
            product.category_id = cmd.category_id
        if cmd.image_url is not None:
            product.image_url = cmd.image_url
        if cmd.attributes is not None:
            product.attributes = {**product.attributes, **cmd.attributes}

        return self._repo.save(product)

    def delete_product(self, product_id: int) -> None:
        found = self._repo.delete(product_id)
        if not found:
            raise ProductNotFound(f"Sản phẩm #{product_id} không tồn tại")
