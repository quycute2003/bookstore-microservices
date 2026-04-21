from django.urls import path, include

urlpatterns = [
    path('', include('modules.customer.presentation.api.urls')),
    path('', include('modules.staff.presentation.api.urls')),
    path('', include('modules.admin.presentation.api.urls')),
]
