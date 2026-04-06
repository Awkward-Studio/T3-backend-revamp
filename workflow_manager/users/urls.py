from django.urls import path
from .views import (
    LabelListCreate,
    LabelDetail,
    UserListCreate,
    UserDetail,
)

urlpatterns = [
    # Labels
    path("api/labels/", LabelListCreate.as_view(), name="label-list"),
    path("api/labels/<int:pk>/", LabelDetail.as_view(), name="label-detail"),
    # Users
    path("api/users/", UserListCreate.as_view(), name="user-list"),
    path("api/users/<int:pk>/", UserDetail.as_view(), name="user-detail"),
]
