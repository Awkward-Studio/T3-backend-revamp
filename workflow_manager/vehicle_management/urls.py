# yourapp/urls.py
from django.urls import path
from .views import (
    CarListView,
    CarCreateView,
    CarDetailView,
    CarUpdateView,
    CarDeleteView,
    TempCarListView,
    TempCarCreateView,
    TempCarDetailView,
    TempCarUpdateView,
    TempCarDeleteView,
)

urlpatterns = [
    # permanent cars
    path("cars/", CarListView.as_view(), name="car-list"),
    path("cars/create/", CarCreateView.as_view(), name="car-create"),
    path("cars/<int:pk>/", CarDetailView.as_view(), name="car-detail"),
    path("cars/<int:pk>/update/", CarUpdateView.as_view(), name="car-update"),
    path("cars/<int:pk>/delete/", CarDeleteView.as_view(), name="car-delete"),
    # in-flight temp cars
    path("temp-cars/", TempCarListView.as_view(), name="temp-car-list"),
    path("temp-cars/create/", TempCarCreateView.as_view(), name="temp-car-create"),
    path(
        "temp-cars/<int:pk>/", TempCarDetailView.as_view(), name="temp-car-detail"
    ),
    path(
        "temp-cars/<int:pk>/update/",
        TempCarUpdateView.as_view(),
        name="temp-car-update",
    ),
    path(
        "temp-cars/<int:pk>/delete/",
        TempCarDeleteView.as_view(),
        name="temp-car-delete",
    ),
]
