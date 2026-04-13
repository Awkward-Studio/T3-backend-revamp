from django.urls import path
from .views import (
    GetNextInvoiceNumberView,
    CreateInvoiceView,
    InvoiceListView,
    InvoiceDetailView,
)

urlpatterns = [
    path(
        "jobcards/<uuid:jobcard_id>/invoices/next-number/",
        GetNextInvoiceNumberView.as_view(),
        name="invoice-next-number",
    ),
    path(
        "invoices/create/",
        CreateInvoiceView.as_view(),
        name="invoice-create",
    ),
    path(
        "jobcards/<uuid:jobcard_id>/invoices/",
        InvoiceListView.as_view(),
        name="invoice-list",
    ),
    path(
        "invoices/<uuid:invoice_id>/",
        InvoiceDetailView.as_view(),
        name="invoice-detail",
    ),
]
