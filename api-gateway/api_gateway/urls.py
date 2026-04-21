from django.contrib import admin
from django.urls import path
from . import views
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # --- Định tuyến Khách hàng ---
    path('', views.home, name='home'),                                 # http://localhost:8000/
    path('health/', views.health_check, name='health_check'),          # http://localhost:8000/health/
    path('auth/', views.auth_view, name='auth'),                       # http://localhost:8000/auth/
    path('product/<str:product_id>/', views.product_detail, name='product_detail'), # http://localhost:8000/product/P01/
    path('listing/', views.listing_view, name='listing'),              # http://localhost:8000/listing/
    path('cart/', views.cart_view, name='cart'),                       # http://localhost:8000/cart/
    path('checkout/', views.checkout_view, name='checkout'),           # http://localhost:8000/checkout/
    path('orders/', views.orders_view, name='orders'),       
    # Đường dẫn trang Đăng nhập / Đăng xuất
    path('login/', views.login_view),
    path('logout/', views.logout_view, name='logout'),
    path('track/', views.track_behavior, name='track_behavior'),
    path('recommendations/', views.recommendations_view, name='recommendations'),
    
    # --- Định tuyến Ban quản trị ---
    path('staff/', views.staff_dashboard, name='staff_dashboard'),     # http://localhost:8000/staff/
    path('manager/', views.manager_dashboard, name='manager_dashboard'),# http://localhost:8000/manager/

    # --- TÀI LIỆU API (SWAGGER/REDOC) ---
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # ĐƯỜNG HẦM VẠN NĂNG (Hứng mọi thể loại API từ Frontend)
    # Cấu trúc: /api/<tên_service>/<đường_dẫn_thực_tế>
    path('api/<str:service_name>/<path:path>', views.universal_proxy),
]