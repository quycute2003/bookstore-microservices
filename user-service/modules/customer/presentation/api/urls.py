from django.urls import path
from .views.customer_view import CustomerListCreateView, CustomerDetailView

urlpatterns = [
    path('customers/',      CustomerListCreateView.as_view()),
    path('customers/<int:pk>/', CustomerDetailView.as_view()),
]
