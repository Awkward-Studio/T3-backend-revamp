from django.db import DatabaseError, IntegrityError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from catalog.models.labour_models import Labour
from catalog.serializers.labour_serializers import LabourSerializer


@extend_schema_view(
    get=extend_schema(
        summary="List all labours",
        description="Retrieve a list of all labour records.",
        tags=["Labours"],
        responses={200: LabourSerializer(many=True)},
    ),
)
class LabourListView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LabourSerializer

    def get(self, request):
        try:
            labours = Labour.objects.all()
            serializer = self.get_serializer(labours, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError:
            return Response(
                {"error": "Could not fetch labour records."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LabourCreateView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LabourSerializer

    @extend_schema(
        summary="Create a labour",
        description="Create a new labour record.",
        tags=["Labours"],
        request=LabourSerializer,
        responses={201: LabourSerializer},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            labour = serializer.save()
            return Response(
                self.get_serializer(labour).data, status=status.HTTP_201_CREATED
            )
        except IntegrityError:
            return Response(
                {"error": "A labour with that code already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to create labour right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LabourDetailView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LabourSerializer

    @extend_schema(
        summary="Retrieve a labour",
        description="Get detailed information about a specific labour record.",
        tags=["Labours"],
        responses={200: LabourSerializer},
    )
    def get(self, request, pk):
        labour = get_object_or_404(Labour, pk=pk)
        serializer = self.get_serializer(labour)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LabourUpdateView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LabourSerializer

    @extend_schema(
        summary="Update a labour",
        description="Update all fields of a labour record.",
        tags=["Labours"],
        request=LabourSerializer,
        responses={200: LabourSerializer},
    )
    def put(self, request, pk):
        labour = get_object_or_404(Labour, pk=pk)
        serializer = self.get_serializer(labour, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            labour = serializer.save()
            return Response(self.get_serializer(labour).data, status=status.HTTP_200_OK)
        except IntegrityError:
            return Response(
                {"error": "Labour code conflicts with an existing record."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to update labour right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Partially update a labour",
        description="Update specific fields of a labour record.",
        tags=["Labours"],
        request=LabourSerializer,
        responses={200: LabourSerializer},
    )
    def patch(self, request, pk):
        labour = get_object_or_404(Labour, pk=pk)
        serializer = self.get_serializer(labour, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            labour = serializer.save()
            return Response(self.get_serializer(labour).data, status=status.HTTP_200_OK)
        except IntegrityError:
            return Response(
                {"error": "Labour code conflicts with an existing record."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to partially update labour right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LabourDeleteView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LabourSerializer

    @extend_schema(
        summary="Delete a labour",
        description="Delete a labour record.",
        tags=["Labours"],
        responses={204: None},
    )
    def delete(self, request, pk):
        labour = get_object_or_404(Labour, pk=pk)
        try:
            labour.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError:
            return Response(
                {"error": "Unable to delete labour right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
