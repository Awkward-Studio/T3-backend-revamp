from django.urls import path
from .views import (
    LabelListCreate,
    LabelDetail,
    UserListCreate,
    UserDetail,
)

urlpatterns = [
    # Labels
    path("labels/", LabelListCreate.as_view(), name="label-list"),
    path("labels/<int:pk>/", LabelDetail.as_view(), name="label-detail"),
    # Users
    path("users/", UserListCreate.as_view(), name="user-list"),
    path("users/<int:pk>/", UserDetail.as_view(), name="user-detail"),
]
