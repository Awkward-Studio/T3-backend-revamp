from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import IntegrityError, DatabaseError, transaction

from catalog.models.insurers_model import InsuranceProvider
from catalog.serializers.insurers_serializers import InsuranceProviderSerializer
from drf_spectacular.utils import extend_schema, extend_schema_view


@extend_schema_view(
    get=extend_schema(
        summary="List all insurance providers",
        description="Retrieve a list of all insurance providers.",
        tags=["InsuranceProviders"],
    ),
)
class InsuranceProviderListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        GET /api/insurance-providers/
        """
        try:
            qs = InsuranceProvider.objects.all()
            serializer = InsuranceProviderSerializer(qs, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError as e:
            return Response(
                {"error": f"Database error fetching providers: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InsuranceProviderCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Create an insurance provider",
        description="Create a new insurance provider record.",
        tags=["InsuranceProviders"],
    )
    def post(self, request):
        """
        POST /api/insurance-providers/create/
        {
          "insurer": "Acme Insurance Ltd",
          "address": "123 Main St, Metropolis",
          "gst": "29ABCDE1234F1Z5"
        }
        """
        serializer = InsuranceProviderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                provider = serializer.save()
            return Response(
                InsuranceProviderSerializer(provider).data,
                status=status.HTTP_201_CREATED,
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


class InsuranceProviderDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Retrieve an insurance provider",
        description="Get detailed information about a specific insurance provider.",
        tags=["InsuranceProviders"],
    )
    def get(self, request, pk):
        """
        GET /api/insurance-providers/{pk}/
        """
        provider = get_object_or_404(InsuranceProvider, id=pk)
        return Response(
            InsuranceProviderSerializer(provider).data, status=status.HTTP_200_OK
        )

    @extend_schema(
        summary="Update an insurance provider",
        description="Update all fields of an insurance provider record.",
        tags=["InsuranceProviders"],
    )
    def put(self, request, pk):
        """
        PUT /api/insurance-providers/{pk}/update/
        Full update of all modifiable fields.
        """
        provider = get_object_or_404(InsuranceProvider, id=pk)
        serializer = InsuranceProviderSerializer(provider, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                updated = serializer.save()
            return Response(
                InsuranceProviderSerializer(updated).data, status=status.HTTP_200_OK
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
    )
    def patch(self, request, pk):
        """
        PATCH /api/insurance-providers/{pk}/partial-update/
        Partial update of one or more fields.
        """
        provider = get_object_or_404(InsuranceProvider, id=pk)
        serializer = InsuranceProviderSerializer(
            provider, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                updated = serializer.save()
            return Response(
                InsuranceProviderSerializer(updated).data, status=status.HTTP_200_OK
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
    )
    def delete(self, request, pk):
        """
        DELETE /api/insurance-providers/{pk}/delete/
        """
        provider = get_object_or_404(InsuranceProvider, id=pk)
        try:
            provider.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError as e:
            return Response(
                {"error": f"Database error deleting provider: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
