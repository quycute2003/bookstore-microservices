from django.urls import path
from .views.staff_view import StaffListCreateView, StaffDetailView, StaffAddProductView

urlpatterns = [
    path('staffs/',               StaffListCreateView.as_view()),
    path('staffs/<int:pk>/',      StaffDetailView.as_view()),
    path('staffs/<int:pk>/add-product/', StaffAddProductView.as_view()),
]
