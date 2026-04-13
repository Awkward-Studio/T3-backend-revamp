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
    path("jobcards/", JobCardListView.as_view(), name="jobcard-list"),
    path("jobcards/create/", JobCardCreateView.as_view(), name="jobcard-create"),
    path("jobcards/<uuid:pk>/", JobCardDetailView.as_view(), name="jobcard-detail"),
    path(
        "jobcards/<uuid:pk>/update/",
        JobCardUpdateView.as_view(),
        name="jobcard-update",
    ),
    path(
        "jobcards/<uuid:pk>/delete/",
        JobCardDeleteView.as_view(),
        name="jobcard-delete",
    ),
    # CurrentPart endpoints
    path("current-parts/", CurrentPartListView.as_view(), name="current-part-list"),
    path(
        "current-parts/create/",
        CurrentPartCreateView.as_view(),
        name="current-part-create",
    ),
    path(
        "current-parts/<uuid:pk>/",
        CurrentPartDetailView.as_view(),
        name="current-part-detail",
    ),
    path(
        "current-parts/<uuid:pk>/update/",
        CurrentPartUpdateView.as_view(),
        name="current-part-update",
    ),
    path(
        "current-parts/<uuid:pk>/delete/",
        CurrentPartDeleteView.as_view(),
        name="current-part-delete",
    ),
    # CurrentLabour endpoints
    path(
        "current-labours/",
        CurrentLabourListView.as_view(),
        name="current-labour-list",
    ),
    path(
        "current-labours/create/",
        CurrentLabourCreateView.as_view(),
        name="current-labour-create",
    ),
    path(
        "current-labours/<uuid:pk>/",
        CurrentLabourDetailView.as_view(),
        name="current-labour-detail",
    ),
    path(
        "current-labours/<uuid:pk>/update/",
        CurrentLabourUpdateView.as_view(),
        name="current-labour-update",
    ),
    path(
        "current-labours/<uuid:pk>/delete/",
        CurrentLabourDeleteView.as_view(),
        name="current-labour-delete",
    ),
    # Add / update / delete CurrentPart snapshots on a JobCard
    path(
        "jobcards/<uuid:jobcard_id>/parts/",
        AddPartsToJobCardView.as_view(),
        name="jobcard-add-parts",
    ),
    # Add / update / delete CurrentLabour snapshots on a JobCard’s TempCar
    path(
        "jobcards/<uuid:jobcard_id>/labours/",
        AddLaboursToJobCardView.as_view(),
        name="jobcard-add-labours",
    ),
    # Finalize JobCard (deduct inventory & mark complete)
    path(
        "jobcards/<uuid:jobcard_id>/finalize/",
        FinalizeJobCardView.as_view(),
        name="jobcard-finalize",
    ),
]
