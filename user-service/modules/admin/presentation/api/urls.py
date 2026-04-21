from django.urls import path
from .views.report_view import ReportListCreateView, ReportDetailView

urlpatterns = [
    path('reports/',          ReportListCreateView.as_view()),
    path('reports/<int:pk>/', ReportDetailView.as_view()),
]
