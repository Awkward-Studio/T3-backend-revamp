from django.urls import path
from catalog.views.insurers_views import (
    InsuranceProviderListView,
    InsuranceProviderCreateView,
    InsuranceProviderDetailView,
)

urlpatterns = [
    # List all providers
    path(
        "api/insurance-providers/",
        InsuranceProviderListView.as_view(),
        name="insuranceprovider-list",
    ),
    # Create a new provider
    path(
        "api/insurance-providers/create/",
        InsuranceProviderCreateView.as_view(),
        name="insuranceprovider-create",
    ),
    # Retrieve details
    path(
        "api/insurance-providers/<uuid:pk>/",
        InsuranceProviderDetailView.as_view(),
        name="insuranceprovider-detail",
    ),
    # Full update
    path(
        "api/insurance-providers/<uuid:pk>/update/",
        InsuranceProviderDetailView.as_view(),
        name="insuranceprovider-update",
    ),
    # Partial update
    path(
        "api/insurance-providers/<uuid:pk>/partial-update/",
        InsuranceProviderDetailView.as_view(),
        name="insuranceprovider-partial-update",
    ),
    # Delete
    path(
        "api/insurance-providers/<uuid:pk>/delete/",
        InsuranceProviderDetailView.as_view(),
        name="insuranceprovider-delete",
    ),
]
