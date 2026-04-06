from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import IntegrityError, DatabaseError, transaction

from catalog.models.vehicle_models_model import VehilceModel
from catalog.serializers.vehicle_models_serializers import VehicleModelSerializer


class VehicleModelsListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        GET /api/vehicleModels/
        """
        try:
            vehicleModels = VehilceModel.objects.all()
            serializer = VehicleModelSerializer(vehicleModels, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError as e:
            return Response(
                {"error": f"Database error fetching vehicleModels: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VehicleModelsCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        POST /api/vehicleModel/create/
        {
          "make": "Audi",
          "models": ["A4","Q5","TT"]
        }
        """
        serializer = VehicleModelSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                vehicleModel = serializer.save()
            return Response(
                VehicleModelSerializer(vehicleModel).data,
                status=status.HTTP_201_CREATED,
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


class VehicleModelsDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """
        GET /api/vehicleModels/{pk}/
        """
        vehicleModel = get_object_or_404(VehilceModel, id=pk)
        return Response(
            VehicleModelSerializer(vehicleModel).data, status=status.HTTP_200_OK
        )

    def put(self, request, pk):
        """
        PUT /api/vehicleModels/{pk}/update/
        Full update of make and models.
        """
        vehicleModel = get_object_or_404(VehilceModel, id=pk)
        serializer = VehicleModelSerializer(vehicleModel, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                updated = serializer.save()
            return Response(
                VehicleModelSerializer(updated).data, status=status.HTTP_200_OK
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

    def patch(self, request, pk):
        """
        PATCH /api/vehicleModels/{pk}/partial-update/
        Partial update of make or models.
        """
        vehicleModel = get_object_or_404(VehilceModel, id=pk)
        serializer = VehicleModelSerializer(
            vehicleModel, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                updated = serializer.save()
            return Response(
                VehicleModelSerializer(updated).data, status=status.HTTP_200_OK
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

    def delete(self, request, pk):
        """
        DELETE /api/vehicleModel/{pk}/delete/
        """
        vehicleModel = get_object_or_404(VehilceModel, id=pk)
        try:
            vehicleModel.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError as e:
            return Response(
                {"error": f"Database error deleting VehicleModel {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
