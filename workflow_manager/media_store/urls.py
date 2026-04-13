from django.urls import path

from .views import AssetUrlView, ImageUploadView, InvoiceUploadView, PdfUploadView


urlpatterns = [
    path("uploads/images/", ImageUploadView.as_view(), name="upload-image"),
    path("uploads/invoices/", InvoiceUploadView.as_view(), name="upload-invoice"),
    path("uploads/pdfs/", PdfUploadView.as_view(), name="upload-pdf"),
    path("uploads/<uuid:asset_id>/", AssetUrlView.as_view(), name="upload-asset-url"),
]
