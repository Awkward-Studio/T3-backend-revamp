from django.db import DatabaseError, IntegrityError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from django.utils import timezone
from users.models import RoleName
from .models import Car, DriverAssignment, DriverExpense, TempCar
from .serializers import (
    CarSerializer,
    DriverAssignmentSerializer,
    DriverExpenseSerializer,
    TempCarSerializer,
)


@extend_schema_view(
    get=extend_schema(
        summary="List all cars",
        description="Retrieve a list of all cars.",
        tags=["Cars"],
        responses={200: CarSerializer(many=True)},
    ),
)
class CarListView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CarSerializer

    def get(self, request):
        try:
            cars = Car.objects.all()
            serializer = self.get_serializer(cars, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError:
            return Response(
                {"error": "Could not fetch cars at this time."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CarCreateView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CarSerializer

    @extend_schema(
        summary="Create a new car",
        description="Create a new car record.",
        tags=["Cars"],
        request=CarSerializer,
        responses={201: CarSerializer},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            car = serializer.save()
            return Response(
                self.get_serializer(car).data, status=status.HTTP_201_CREATED
            )
        except IntegrityError:
            return Response(
                {"error": "A car with that number already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to create car right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CarDetailView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CarSerializer

    @extend_schema(
        summary="Retrieve a car",
        description="Get detailed information about a specific car.",
        tags=["Cars"],
        responses={200: CarSerializer},
    )
    def get(self, request, pk):
        car = get_object_or_404(Car, pk=pk)
        serializer = self.get_serializer(car)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CarUpdateView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CarSerializer

    @extend_schema(
        summary="Update a car",
        description="Update all fields of a car record.",
        tags=["Cars"],
        request=CarSerializer,
        responses={200: CarSerializer},
    )
    def put(self, request, pk):
        car = get_object_or_404(Car, pk=pk)
        serializer = self.get_serializer(car, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            car = serializer.save()
            return Response(self.get_serializer(car).data, status=status.HTTP_200_OK)
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

    @extend_schema(
        summary="Partially update a car",
        description="Update specific fields of a car record.",
        tags=["Cars"],
        request=CarSerializer,
        responses={200: CarSerializer},
    )
    def patch(self, request, pk):
        car = get_object_or_404(Car, pk=pk)
        serializer = self.get_serializer(car, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            car = serializer.save()
            return Response(self.get_serializer(car).data, status=status.HTTP_200_OK)
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


class CarDeleteView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CarSerializer

    @extend_schema(
        summary="Delete a car",
        description="Delete a car record.",
        tags=["Cars"],
        responses={204: None},
    )
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


@extend_schema_view(
    get=extend_schema(
        summary="List all temp cars",
        description="Retrieve a list of all temp cars.",
        tags=["TempCars"],
        responses={200: TempCarSerializer(many=True)},
    ),
)
class TempCarListView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TempCarSerializer

    def get(self, request):
        try:
            temps = TempCar.objects.select_related("car").all()
            serializer = self.get_serializer(temps, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError:
            return Response(
                {"error": "Could not fetch temp cars."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TempCarCreateView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TempCarSerializer

    @extend_schema(
        summary="Create a new temp car",
        description="Create a new temp car record.",
        tags=["TempCars"],
        request=TempCarSerializer,
        responses={201: TempCarSerializer},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            temp = serializer.save()
            return Response(
                self.get_serializer(temp).data, status=status.HTTP_201_CREATED
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


class TempCarDetailView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TempCarSerializer

    @extend_schema(
        summary="Retrieve a temp car",
        description="Get detailed information about a specific temp car.",
        tags=["TempCars"],
        responses={200: TempCarSerializer},
    )
    def get(self, request, pk):
        temp = get_object_or_404(TempCar, pk=pk)
        serializer = self.get_serializer(temp)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TempCarUpdateView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TempCarSerializer

    @extend_schema(
        summary="Update a temp car",
        description="Update all fields of a temp car record.",
        tags=["TempCars"],
        request=TempCarSerializer,
        responses={200: TempCarSerializer},
    )
    def put(self, request, pk):
        temp = get_object_or_404(TempCar, pk=pk)
        serializer = self.get_serializer(temp, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            temp = serializer.save()
            return Response(self.get_serializer(temp).data, status=status.HTTP_200_OK)
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

    @extend_schema(
        summary="Partially update a temp car",
        description="Update specific fields of a temp car record.",
        tags=["TempCars"],
        request=TempCarSerializer,
        responses={200: TempCarSerializer},
    )
    def patch(self, request, pk):
        temp = get_object_or_404(TempCar, pk=pk)
        serializer = self.get_serializer(temp, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            temp = serializer.save()
            return Response(self.get_serializer(temp).data, status=status.HTTP_200_OK)
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


class TempCarDeleteView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TempCarSerializer

    @extend_schema(
        summary="Delete a temp car",
        description="Delete a temp car record.",
        tags=["TempCars"],
        responses={204: None},
    )
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


class DriverAssignmentListCreateView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DriverAssignmentSerializer

    def get(self, request):
        user = request.user
        is_admin = getattr(user, "is_authenticated", False) and user.has_role(RoleName.ADMIN)
        is_driver = getattr(user, "is_authenticated", False) and user.has_role(RoleName.DRIVER)

        qs = DriverAssignment.objects.select_related("driver", "car", "temp_car", "job_card").prefetch_related("expenses")
        if is_driver and not is_admin:
            qs = qs.filter(driver=user)

        assignment_type = request.query_params.get("type")
        if assignment_type:
            qs = qs.filter(assignment_type__iexact=assignment_type)

        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status__iexact=status_param)

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        if not (request.user.has_role(RoleName.ADMIN)):
            return Response(
                {"error": "Only admin can create driver assignments."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        assignment = serializer.save(created_by=request.user)
        return Response(self.get_serializer(assignment).data, status=status.HTTP_201_CREATED)


class DriverAssignmentDetailView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DriverAssignmentSerializer

    def get(self, request, pk):
        assignment = get_object_or_404(
            DriverAssignment.objects.select_related("driver", "car", "temp_car", "job_card").prefetch_related("expenses"),
            pk=pk,
        )
        user = request.user
        is_admin = user.has_role(RoleName.ADMIN)
        is_driver = user.has_role(RoleName.DRIVER)
        if is_driver and not is_admin and assignment.driver_id != user.id:
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        return Response(self.get_serializer(assignment).data)

    def patch(self, request, pk):
        assignment = get_object_or_404(DriverAssignment, pk=pk)
        user = request.user
        is_admin = user.has_role(RoleName.ADMIN)
        is_driver = user.has_role(RoleName.DRIVER)

        if not is_admin and (not is_driver or assignment.driver_id != user.id):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        if assignment.status in [
            DriverAssignment.AssignmentStatus.COMPLETED,
            DriverAssignment.AssignmentStatus.DROPPED,
            DriverAssignment.AssignmentStatus.CANCELLED,
        ] and not is_admin:
            return Response(
                {"error": "Cannot modify completed assignment."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(assignment, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        updated = serializer.save()
        return Response(self.get_serializer(updated).data)


class DriverExpenseListCreateView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DriverExpenseSerializer

    def get(self, request, pk):
        assignment = get_object_or_404(DriverAssignment, pk=pk)
        user = request.user
        is_admin = user.has_role(RoleName.ADMIN)
        is_driver = user.has_role(RoleName.DRIVER)
        if is_driver and not is_admin and assignment.driver_id != user.id:
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        expenses = assignment.expenses.all().order_by("created_at")
        serializer = self.get_serializer(expenses, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        assignment = get_object_or_404(DriverAssignment, pk=pk)
        user = request.user
        is_admin = user.has_role(RoleName.ADMIN)
        is_driver = user.has_role(RoleName.DRIVER)
        if not is_admin and (not is_driver or assignment.driver_id != user.id):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        if assignment.status in [
            DriverAssignment.AssignmentStatus.COMPLETED,
            DriverAssignment.AssignmentStatus.DROPPED,
            DriverAssignment.AssignmentStatus.CANCELLED,
        ] and not is_admin:
            return Response(
                {"error": "Cannot add expenses to completed assignment."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = request.data.copy()
        data["assignment"] = assignment.id
        serializer = self.get_serializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        expense = serializer.save(assignment=assignment, created_by=user)
        return Response(self.get_serializer(expense).data, status=status.HTTP_201_CREATED)
