from django.urls import path
from catalog.views.labour_views import (
    LabourListView,
    LabourCreateView,
    LabourDetailView,
    LabourUpdateView,
    LabourDeleteView,
)

urlpatterns = [
    path("api/labours/", LabourListView.as_view(), name="labour-list"),
    path("api/labours/create/", LabourCreateView.as_view(), name="labour-create"),
    path("api/labours/<uuid:pk>/", LabourDetailView.as_view(), name="labour-detail"),
    path(
        "api/labours/<uuid:pk>/update/",
        LabourUpdateView.as_view(),
        name="labour-update",
    ),
    path(
        "api/labours/<uuid:pk>/delete/",
        LabourDeleteView.as_view(),
        name="labour-delete",
    ),
]
