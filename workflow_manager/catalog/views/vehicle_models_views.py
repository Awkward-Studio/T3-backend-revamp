from django.db import DatabaseError, IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from catalog.models.vehicle_models_model import VehilceModel
from catalog.serializers.vehicle_models_serializers import VehicleModelSerializer


@extend_schema_view(
    get=extend_schema(
        summary="List all vehicle models",
        description="Retrieve a list of all vehicle make/model entries.",
        tags=["VehicleModels"],
        responses={200: VehicleModelSerializer(many=True)},
    ),
)
class VehicleModelsListView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VehicleModelSerializer

    def get(self, request):
        try:
            vehicle_models = VehilceModel.objects.all()
            serializer = self.get_serializer(vehicle_models, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError as e:
            return Response(
                {"error": f"Database error fetching vehicleModels: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VehicleModelsCreateView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VehicleModelSerializer

    @extend_schema(
        summary="Create a vehicle model entry",
        description="Create a new vehicle make/model entry.",
        tags=["VehicleModels"],
        request=VehicleModelSerializer,
        responses={201: VehicleModelSerializer},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                vehicle_model = serializer.save()
            return Response(
                self.get_serializer(vehicle_model).data, status=status.HTTP_201_CREATED
            )
        except IntegrityError as e:
            return Response(
                {"error": f"Integrity error creating vehicleModel: {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError as e:
            return Response(
                {"error": f"Database error creating vehicleModel: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VehicleModelsDetailView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VehicleModelSerializer

    @extend_schema(
        summary="Retrieve a vehicle model entry",
        description="Get detailed information about a specific vehicle make/model entry.",
        tags=["VehicleModels"],
        responses={200: VehicleModelSerializer},
    )
    def get(self, request, pk):
        vehicle_model = get_object_or_404(VehilceModel, id=pk)
        return Response(
            self.get_serializer(vehicle_model).data, status=status.HTTP_200_OK
        )

    @extend_schema(
        summary="Update a vehicle model entry",
        description="Update all fields of a vehicle make/model entry.",
        tags=["VehicleModels"],
        request=VehicleModelSerializer,
        responses={200: VehicleModelSerializer},
    )
    def put(self, request, pk):
        vehicle_model = get_object_or_404(VehilceModel, id=pk)
        serializer = self.get_serializer(vehicle_model, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                updated = serializer.save()
            return Response(
                self.get_serializer(updated).data, status=status.HTTP_200_OK
            )
        except IntegrityError as e:
            return Response(
                {"error": f"Integrity error updating vehicleModel: {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError as e:
            return Response(
                {"error": f"Database error updating vehicleModel: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Partially update a vehicle model entry",
        description="Update specific fields of a vehicle make/model entry.",
        tags=["VehicleModels"],
        request=VehicleModelSerializer,
        responses={200: VehicleModelSerializer},
    )
    def patch(self, request, pk):
        vehicle_model = get_object_or_404(VehilceModel, id=pk)
        serializer = self.get_serializer(vehicle_model, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                updated = serializer.save()
            return Response(
                self.get_serializer(updated).data, status=status.HTTP_200_OK
            )
        except IntegrityError as e:
            return Response(
                {"error": f"Integrity error patching VehicleModel: {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError as e:
            return Response(
                {"error": f"Database error patching VehicleModel: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Delete a vehicle model entry",
        description="Delete a vehicle make/model entry.",
        tags=["VehicleModels"],
        responses={204: None},
    )
    def delete(self, request, pk):
        vehicle_model = get_object_or_404(VehilceModel, id=pk)
        try:
            vehicle_model.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError as e:
            return Response(
                {"error": f"Database error deleting VehicleModel {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
