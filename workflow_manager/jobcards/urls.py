# yourapp/urls.py
from django.urls import path
from .views import (
    JobCardListView,
    JobCardCreateView,
    JobCardDetailView,
    JobCardUpdateView,
    JobCardDeleteView,
    CurrentPartListView,
    CurrentPartCreateView,
    CurrentPartDetailView,
    CurrentPartUpdateView,
    CurrentPartDeleteView,
    CurrentLabourListView,
    CurrentLabourCreateView,
    CurrentLabourDetailView,
    CurrentLabourUpdateView,
    CurrentLabourDeleteView,
    AddPartsToJobCardView,
    AddLaboursToJobCardView,
    FinalizeJobCardView,
)

urlpatterns = [
    # JobCard endpoints
    path("api/jobcards/", JobCardListView.as_view(), name="jobcard-list"),
    path("api/jobcards/create/", JobCardCreateView.as_view(), name="jobcard-create"),
    path("api/jobcards/<uuid:pk>/", JobCardDetailView.as_view(), name="jobcard-detail"),
    path(
        "api/jobcards/<uuid:pk>/update/",
        JobCardUpdateView.as_view(),
        name="jobcard-update",
    ),
    path(
        "api/jobcards/<uuid:pk>/delete/",
        JobCardDeleteView.as_view(),
        name="jobcard-delete",
    ),
    # CurrentPart endpoints
    path("api/current-parts/", CurrentPartListView.as_view(), name="current-part-list"),
    path(
        "api/current-parts/create/",
        CurrentPartCreateView.as_view(),
        name="current-part-create",
    ),
    path(
        "api/current-parts/<uuid:pk>/",
        CurrentPartDetailView.as_view(),
        name="current-part-detail",
    ),
    path(
        "api/current-parts/<uuid:pk>/update/",
        CurrentPartUpdateView.as_view(),
        name="current-part-update",
    ),
    path(
        "api/current-parts/<uuid:pk>/delete/",
        CurrentPartDeleteView.as_view(),
        name="current-part-delete",
    ),
    # CurrentLabour endpoints
    path(
        "api/current-labours/",
        CurrentLabourListView.as_view(),
        name="current-labour-list",
    ),
    path(
        "api/current-labours/create/",
        CurrentLabourCreateView.as_view(),
        name="current-labour-create",
    ),
    path(
        "api/current-labours/<uuid:pk>/",
        CurrentLabourDetailView.as_view(),
        name="current-labour-detail",
    ),
    path(
        "api/current-labours/<uuid:pk>/update/",
        CurrentLabourUpdateView.as_view(),
        name="current-labour-update",
    ),
    path(
        "api/current-labours/<uuid:pk>/delete/",
        CurrentLabourDeleteView.as_view(),
        name="current-labour-delete",
    ),
    # Add / update / delete CurrentPart snapshots on a JobCard
    path(
        "api/jobcards/<uuid:jobcard_id>/parts/",
        AddPartsToJobCardView.as_view(),
        name="jobcard-add-parts",
    ),
    # Add / update / delete CurrentLabour snapshots on a JobCard’s TempCar
    path(
        "api/jobcards/<uuid:jobcard_id>/labours/",
        AddLaboursToJobCardView.as_view(),
        name="jobcard-add-labours",
    ),
    # Finalize JobCard (deduct inventory & mark complete)
    path(
        "api/jobcards/<uuid:jobcard_id>/finalize/",
        FinalizeJobCardView.as_view(),
        name="jobcard-finalize",
    ),
]
