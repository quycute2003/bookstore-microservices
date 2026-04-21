"""
Presentation Views
===================
3 nhóm endpoint:
  1. /books/, /clothes/   → backward-compat với các service cũ
  2. /products/           → unified endpoint (tất cả loại)
  3. /<type>/             → 8 loại mới dùng factory view chung
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from modules.catalog.application.services.product_service import ProductService, ProductNotFound
from modules.catalog.application.commands.create_product import CreateProductCommand
from modules.catalog.application.commands.update_product import UpdateProductCommand
from modules.catalog.application.queries.list_products import ListProductsQuery
from modules.catalog.application.queries.get_product import GetProductQuery
from modules.catalog.infrastructure.repositories.product_repository_impl import ProductRepositoryImpl
from modules.catalog.presentation.api.serializers.product_serializer import (
    BookInputSerializer, BookOutputSerializer,
    ClothInputSerializer, ClothOutputSerializer,
    ProductOutputSerializer, GenericProductInputSerializer,
)


def _make_service() -> ProductService:
    return ProductService(ProductRepositoryImpl())


# =========================================================
# BOOKS  (backward-compat)
# =========================================================

class BookListCreateView(APIView):

    def get(self, request):
        cat_id = request.query_params.get('category_id')
        query = ListProductsQuery(product_type='book', category_id=int(cat_id) if cat_id else None)
        products = _make_service().list_products(query)
        return Response(BookOutputSerializer(products, many=True).data)

    def post(self, request):
        ser = BookInputSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        product = _make_service().create_product(CreateProductCommand(**ser.to_command_data()))
        return Response(BookOutputSerializer(product).data, status=status.HTTP_201_CREATED)


class BookDetailView(APIView):

    def get(self, request, pk):
        try:
            product = _make_service().get_product(GetProductQuery(pk))
            if product.product_type != 'book':
                return Response({"error": "Sách không tồn tại!"}, status=status.HTTP_404_NOT_FOUND)
            return Response(BookOutputSerializer(product).data)
        except ProductNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        try:
            svc = _make_service()
            svc.get_product(GetProductQuery(pk))
        except ProductNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        ser = BookInputSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        d = ser.validated_data
        cmd = UpdateProductCommand(
            product_id=pk, name=d.get("title"), price=d.get("price"),
            stock=d.get("stock"), category_id=d.get("category_id"),
            image_url=d.get("image_url"),
            attributes={"author": d["author"], "isbn": d.get("isbn")} if "author" in d else None,
        )
        return Response(BookOutputSerializer(svc.update_product(cmd)).data)

    def delete(self, request, pk):
        try:
            _make_service().delete_product(pk)
            return Response({"message": f"Đã xóa sách #{pk}!"})
        except ProductNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)


# =========================================================
# CLOTHES  (backward-compat)
# =========================================================

class ClothListCreateView(APIView):

    def get(self, request):
        cat_id = request.query_params.get('category_id')
        query = ListProductsQuery(product_type='cloth', category_id=int(cat_id) if cat_id else None)
        products = _make_service().list_products(query)
        return Response(ClothOutputSerializer(products, many=True).data)

    def post(self, request):
        ser = ClothInputSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        product = _make_service().create_product(CreateProductCommand(**ser.to_command_data()))
        return Response(ClothOutputSerializer(product).data, status=status.HTTP_201_CREATED)


class ClothDetailView(APIView):

    def get(self, request, pk):
        try:
            product = _make_service().get_product(GetProductQuery(pk))
            if product.product_type != 'cloth':
                return Response({"error": "Sản phẩm không tồn tại!"}, status=status.HTTP_404_NOT_FOUND)
            return Response(ClothOutputSerializer(product).data)
        except ProductNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        try:
            svc = _make_service()
            svc.get_product(GetProductQuery(pk))
        except ProductNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        ser = ClothInputSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        d = ser.validated_data
        attrs = {k: d[k] for k in ("brand", "size", "color") if k in d}
        cmd = UpdateProductCommand(
            product_id=pk, name=d.get("name"), price=d.get("price"),
            stock=d.get("stock"), category_id=d.get("category_id"),
            image_url=d.get("image_url"), attributes=attrs or None,
        )
        return Response(ClothOutputSerializer(svc.update_product(cmd)).data)

    def delete(self, request, pk):
        try:
            _make_service().delete_product(pk)
            return Response({"message": f"Đã xóa sản phẩm #{pk}!"})
        except ProductNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)


# =========================================================
# FACTORY VIEW — dùng cho 8 loại mới (stationery, electronics, …)
# =========================================================

def _make_list_view(ptype: str):
    """Tạo view GET/POST cho một product_type cụ thể."""

    class _ListView(APIView):
        def get(self, request):
            cat_id = request.query_params.get('category_id')
            query = ListProductsQuery(product_type=ptype, category_id=int(cat_id) if cat_id else None)
            products = _make_service().list_products(query)
            return Response(ProductOutputSerializer(products, many=True).data)

        def post(self, request):
            ser = GenericProductInputSerializer(data=request.data)
            if not ser.is_valid():
                return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
            cmd = CreateProductCommand(**ser.to_command_data(ptype))
            product = _make_service().create_product(cmd)
            return Response(ProductOutputSerializer(product).data, status=status.HTTP_201_CREATED)

    _ListView.__name__ = f"{ptype.title()}ListView"
    return _ListView.as_view()


def _make_detail_view(ptype: str):
    """Tạo view GET/PUT/DELETE cho một product_type cụ thể."""

    class _DetailView(APIView):
        def get(self, request, pk):
            try:
                product = _make_service().get_product(GetProductQuery(pk))
                if product.product_type != ptype:
                    return Response({"error": "Sản phẩm không tồn tại!"}, status=status.HTTP_404_NOT_FOUND)
                return Response(ProductOutputSerializer(product).data)
            except ProductNotFound as e:
                return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

        def put(self, request, pk):
            try:
                svc = _make_service()
                svc.get_product(GetProductQuery(pk))
            except ProductNotFound as e:
                return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
            ser = GenericProductInputSerializer(data=request.data, partial=True)
            if not ser.is_valid():
                return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
            d = ser.validated_data
            cmd = UpdateProductCommand(
                product_id=pk, name=d.get("name"), price=d.get("price"),
                stock=d.get("stock"), category_id=d.get("category_id"),
                image_url=d.get("image_url"), attributes=d.get("attributes"),
            )
            return Response(ProductOutputSerializer(svc.update_product(cmd)).data)

        def delete(self, request, pk):
            try:
                _make_service().delete_product(pk)
                return Response({"message": f"Đã xóa {ptype} #{pk}!"})
            except ProductNotFound as e:
                return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    _DetailView.__name__ = f"{ptype.title()}DetailView"
    return _DetailView.as_view()


# =========================================================
# UNIFIED  (tất cả loại — cho AI service)
# =========================================================

class ProductListView(APIView):
    """GET /products/?type=<ptype> — trả tất cả hoặc lọc theo type."""

    def get(self, request):
        product_type = request.query_params.get('type')
        cat_id = request.query_params.get('category_id')
        query = ListProductsQuery(
            product_type=product_type,
            category_id=int(cat_id) if cat_id else None,
        )
        products = _make_service().list_products(query)
        return Response(ProductOutputSerializer(products, many=True).data)


class ProductDetailView(APIView):
    """GET /products/<id>/ — trả product bất kể type."""

    def get(self, request, pk):
        try:
            product = _make_service().get_product(GetProductQuery(pk))
            return Response(ProductOutputSerializer(product).data)
        except ProductNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
