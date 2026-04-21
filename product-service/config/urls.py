from django.urls import path, include

urlpatterns = [
    path('', include('modules.catalog.presentation.api.urls')),
]
