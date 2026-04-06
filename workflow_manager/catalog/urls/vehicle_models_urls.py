from django.urls import path
from catalog.views.vehicle_models_views import (
    VehicleModelsListView,
    VehicleModelsCreateView,
    VehicleModelsDetailView,
)

urlpatterns = [
    # List all vehicle-models
    path(
        "api/vehicle-models/",
        VehicleModelsListView.as_view(),
        name="vehicle-models-list",
    ),
    # Create a new vehicle-models entry
    path(
        "api/vehicle-models/create/",
        VehicleModelsCreateView.as_view(),
        name="vehicle-models-create",
    ),
    # Retrieve details
    path(
        "api/vehicle-models/<uuid:pk>/",
        VehicleModelsDetailView.as_view(),
        name="vehicle-models-detail",
    ),
    # Full update
    path(
        "api/vehicle-models/<uuid:pk>/update/",
        VehicleModelsDetailView.as_view(),
        name="vehicle-models-update",
    ),
    # Partial update
    path(
        "api/vehicle-models/<uuid:pk>/partial-update/",
        VehicleModelsDetailView.as_view(),
        name="vehicle-models-partial-update",
    ),
    # Delete
    path(
        "api/vehicle-models/<uuid:pk>/delete/",
        VehicleModelsDetailView.as_view(),
        name="vehicle-models-delete",
    ),
]
