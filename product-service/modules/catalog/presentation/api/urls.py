from django.urls import path
from modules.catalog.presentation.api.views.product_view import (
    BookListCreateView, BookDetailView,
    ClothListCreateView, ClothDetailView,
    ProductListView, ProductDetailView,
    _make_list_view, _make_detail_view,
)

# 8 loại mới
NEW_TYPES = ['stationery', 'electronics', 'toy', 'cosmetic', 'bag', 'shoe', 'watch', 'gift']

urlpatterns = [
    # Backward-compat: book-service / clothes-service cũ
    path('books/',          BookListCreateView.as_view()),
    path('books/<int:pk>/', BookDetailView.as_view()),
    path('clothes/',          ClothListCreateView.as_view()),
    path('clothes/<int:pk>/', ClothDetailView.as_view()),

    # Unified endpoint (tất cả loại — AI service)
    path('products/',          ProductListView.as_view()),
    path('products/<int:pk>/', ProductDetailView.as_view()),
]

# Tự động tạo /stationery/, /electronics/, … cho 8 loại mới
for _ptype in NEW_TYPES:
    urlpatterns += [
        path(f'{_ptype}/',          _make_list_view(_ptype)),
        path(f'{_ptype}/<int:pk>/', _make_detail_view(_ptype)),
    ]
