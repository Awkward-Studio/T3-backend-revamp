from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import IntegrityError, DatabaseError

from catalog.models.labour_models import Labour
from catalog.serializers.labour_serializers import LabourSerializer


class LabourListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        GET /api/labours/
        """
        try:
            labours = Labour.objects.all()
            serializer = LabourSerializer(labours, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError:
            return Response(
                {"error": "Could not fetch labour records."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LabourCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        POST /api/labours/create/
        """
        serializer = LabourSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            labour = serializer.save()
            return Response(
                LabourSerializer(labour).data, status=status.HTTP_201_CREATED
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


class LabourDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """
        GET /api/labours/{pk}/
        """
        labour = get_object_or_404(Labour, pk=pk)
        serializer = LabourSerializer(labour)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LabourUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        """
        PUT /api/labours/{pk}/update/
        Full update
        """
        labour = get_object_or_404(Labour, pk=pk)
        serializer = LabourSerializer(labour, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            labour = serializer.save()
            return Response(LabourSerializer(labour).data, status=status.HTTP_200_OK)
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

    def patch(self, request, pk):
        """
        PATCH /api/labours/{pk}/update/
        Partial update
        """
        labour = get_object_or_404(Labour, pk=pk)
        serializer = LabourSerializer(labour, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            labour = serializer.save()
            return Response(LabourSerializer(labour).data, status=status.HTTP_200_OK)
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


class LabourDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        """
        DELETE /api/labours/{pk}/delete/
        """
        labour = get_object_or_404(Labour, pk=pk)
        try:
            labour.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError:
            return Response(
                {"error": "Unable to delete labour right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
