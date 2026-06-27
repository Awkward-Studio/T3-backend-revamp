from django.urls import path

from .views import (
    CreateInvoiceView,
    CustomerWalletAddCreditView,
    CustomerWalletDetailView,
    CustomerWalletListView,
    GetNextInvoiceNumberView,
    InvoiceDetailView,
    InvoiceListView,
)

urlpatterns = [
    path("wallets/", CustomerWalletListView.as_view(), name="wallet-list"),
    path(
        "wallets/<int:car_id>/",
        CustomerWalletDetailView.as_view(),
        name="wallet-detail",
    ),
    path(
        "wallets/<int:car_id>/credits/",
        CustomerWalletAddCreditView.as_view(),
        name="wallet-add-credit",
    ),
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
