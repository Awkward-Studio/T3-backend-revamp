# yourapp/views.py
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import IntegrityError, DatabaseError

from .models import Car, TempCar
from .serializers import CarSerializer, TempCarSerializer


# ─── CARS ────────────────────────────────────────────────────


class CarListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            cars = Car.objects.all()
            serializer = CarSerializer(cars, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except DatabaseError:
            return Response(
                {"error": "Could not fetch cars at this time."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CarCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CarSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            car = serializer.save()
            return Response(CarSerializer(car).data, status=status.HTTP_201_CREATED)
        except IntegrityError as e:
            return Response(
                {"error": "A car with that number already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to create car right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CarDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        car = get_object_or_404(Car, pk=pk)
        serializer = CarSerializer(car)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CarUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        car = get_object_or_404(Car, pk=pk)
        serializer = CarSerializer(car, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            car = serializer.save()
            return Response(CarSerializer(car).data, status=status.HTTP_200_OK)
        except IntegrityError:
            return Response(
                {"error": "That car number conflicts with an existing record."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to update car right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request, pk):
        car = get_object_or_404(Car, pk=pk)
        serializer = CarSerializer(car, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            car = serializer.save()
            return Response(CarSerializer(car).data, status=status.HTTP_200_OK)
        except IntegrityError:
            return Response(
                {"error": "That car number conflicts with an existing record."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to partially update car right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CarDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        car = get_object_or_404(Car, pk=pk)
        try:
            car.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError:
            return Response(
                {"error": "Unable to delete car right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ─── TEMP CARS ───────────────────────────────────────────────


class TempCarListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            temps = TempCar.objects.select_related("car").all()
            serializer = TempCarSerializer(temps, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError:
            return Response(
                {"error": "Could not fetch temp cars."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TempCarCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = TempCarSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            temp = serializer.save()
            return Response(
                TempCarSerializer(temp).data, status=status.HTTP_201_CREATED
            )
        except IntegrityError:
            return Response(
                {"error": "Integrity error creating temp car."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to create temp car right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TempCarDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        temp = get_object_or_404(TempCar, pk=pk)
        serializer = TempCarSerializer(temp)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TempCarUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        temp = get_object_or_404(TempCar, pk=pk)
        serializer = TempCarSerializer(temp, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            temp = serializer.save()
            return Response(TempCarSerializer(temp).data, status=status.HTTP_200_OK)
        except IntegrityError:
            return Response(
                {"error": "Integrity error updating temp car."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to update temp car right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request, pk):
        temp = get_object_or_404(TempCar, pk=pk)
        serializer = TempCarSerializer(temp, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            temp = serializer.save()
            return Response(TempCarSerializer(temp).data, status=status.HTTP_200_OK)
        except IntegrityError:
            return Response(
                {"error": "Integrity error patching temp car."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to patch temp car right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TempCarDeleteView(APIView):
    # TODO: Add jobcard data transfer
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        temp = get_object_or_404(TempCar, pk=pk)
        try:
            temp.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError:
            return Response(
                {"error": "Unable to delete temp car right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
