from django.urls import path
from .views import (
    ProductListView,
    ProductCreateView,
    ProductDetailView,
    ProductUpdateView,
    ProductDeleteView,
    ProductCsvUploadView,
)

urlpatterns = [
    path("products/", ProductListView.as_view(), name="product-list"),
    path("products/create/", ProductCreateView.as_view(), name="product-create"),
    path("products/<uuid:pk>/", ProductDetailView.as_view(), name="product-detail"),
    path(
        "products/<uuid:pk>/update/", ProductUpdateView.as_view(), name="product-update"
    ),
    path(
        "products/<uuid:pk>/delete/", ProductDeleteView.as_view(), name="product-delete"
    ),
    path(
        "products/upload-products-csv/",
        ProductCsvUploadView.as_view(),
        name="upload_products_csv",
    ),
]
