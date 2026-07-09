from django.db import DatabaseError, IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from catalog.models.insurers_model import InsuranceProvider
from catalog.serializers.insurers_serializers import InsuranceProviderSerializer


@extend_schema_view(
    get=extend_schema(
        summary="List all insurance providers",
        description="Retrieve a list of all insurance providers.",
        tags=["InsuranceProviders"],
        responses={200: InsuranceProviderSerializer(many=True)},
    ),
)
class InsuranceProviderListView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InsuranceProviderSerializer

    def get(self, request):
        try:
            qs = InsuranceProvider.objects.all()
            serializer = self.get_serializer(qs, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError as e:
            return Response(
                {"error": f"Database error fetching providers: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InsuranceProviderCreateView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InsuranceProviderSerializer

    @extend_schema(
        summary="Create an insurance provider",
        description="Create a new insurance provider record.",
        tags=["InsuranceProviders"],
        request=InsuranceProviderSerializer,
        responses={201: InsuranceProviderSerializer},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                provider = serializer.save()
            return Response(
                self.get_serializer(provider).data, status=status.HTTP_201_CREATED
            )
        except IntegrityError as e:
            return Response(
                {"error": f"Integrity error creating provider: {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError as e:
            return Response(
                {"error": f"Database error creating provider: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InsuranceProviderDetailView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InsuranceProviderSerializer

    @extend_schema(
        summary="Retrieve an insurance provider",
        description="Get detailed information about a specific insurance provider.",
        tags=["InsuranceProviders"],
        responses={200: InsuranceProviderSerializer},
    )
    def get(self, request, pk):
        provider = get_object_or_404(InsuranceProvider, id=pk)
        return Response(self.get_serializer(provider).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Update an insurance provider",
        description="Update all fields of an insurance provider record.",
        tags=["InsuranceProviders"],
        request=InsuranceProviderSerializer,
        responses={200: InsuranceProviderSerializer},
    )
    def put(self, request, pk):
        provider = get_object_or_404(InsuranceProvider, id=pk)
        serializer = self.get_serializer(provider, data=request.data)
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
                {"error": f"Integrity error updating provider: {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError as e:
            return Response(
                {"error": f"Database error updating provider: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Partially update an insurance provider",
        description="Update specific fields of an insurance provider record.",
        tags=["InsuranceProviders"],
        request=InsuranceProviderSerializer,
        responses={200: InsuranceProviderSerializer},
    )
    def patch(self, request, pk):
        provider = get_object_or_404(InsuranceProvider, id=pk)
        serializer = self.get_serializer(provider, data=request.data, partial=True)
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
                {"error": f"Integrity error patching provider: {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError as e:
            return Response(
                {"error": f"Database error patching provider: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Delete an insurance provider",
        description="Delete an insurance provider record.",
        tags=["InsuranceProviders"],
        responses={204: None},
    )
    def delete(self, request, pk):
        provider = get_object_or_404(InsuranceProvider, id=pk)
        try:
            provider.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError as e:
            return Response(
                {"error": f"Database error deleting provider: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
