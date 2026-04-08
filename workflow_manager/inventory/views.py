from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
import csv
import io
from datetime import datetime

from .models import Product
from .serializers import (
    ProductListSerializer,
    ProductCreateSerializer,
    ProductDetailSerializer,
    ProductUpdateSerializer,
)

from .filters import ProductFilter
from drf_spectacular.utils import extend_schema, extend_schema_view


@extend_schema_view(
    get=extend_schema(
        summary="List all products",
        description="Retrieve a list of all products with optional filtering, search, and ordering.",
        tags=["Products"],
    ),
)
class ProductListView(APIView):
    """
    Handle GET requests to list all products with:
    - Filtering (price range, category, name, creation date)
    - Searching (name or other fields)
    - Ordering (ascending/descending)
    """

    permission_classes = [AllowAny]

    def get(self, request):
        products = Product.objects.all()

        # Apply filters using django-filter
        filterset = ProductFilter(data=request.GET, queryset=products)
        if filterset.is_valid():
            products = filterset.qs
        else:
            return Response(filterset.errors, status=400)

        # Apply ordering
        ordering = request.GET.get("ordering")
        if ordering:
            products = products.order_by(ordering)

        # Serialize and return the response
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data, status=200)


class ProductCreateView(APIView):
    """
    Handle POST requests to create a new product.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Create a new product",
        description="Create a new product record (single or bulk).",
        tags=["Products"],
    )
    def post(self, request):
        if isinstance(
            request.data, list
        ):  # Check if the request is for multiple entries
            serializer = ProductCreateSerializer(data=request.data, many=True)
        else:  # Single product creation
            serializer = ProductCreateSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProductDetailView(APIView):
    """
    Handle GET requests to retrieve a specific product.
    """

    @extend_schema(
        summary="Retrieve a product",
        description="Get detailed information about a specific product.",
        tags=["Products"],
    )
    def get(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
            serializer = ProductDetailSerializer(product)
            return Response(serializer.data)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND
            )


class ProductUpdateView(APIView):
    """
    Handle PUT requests to update a product.
    """

    @extend_schema(
        summary="Partially update a product",
        description="Update specific fields of a product record.",
        tags=["Products"],
    )
    def patch(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = ProductUpdateSerializer(product, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProductDeleteView(APIView):
    """
    Handle DELETE requests to delete a product.
    """

    @extend_schema(
        summary="Delete a product",
        description="Delete a product record.",
        tags=["Products"],
    )
    def delete(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
            product.delete()
            return Response(
                {"message": "Product deleted successfully"},
                status=status.HTTP_204_NO_CONTENT,
            )
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND
            )


class ProductCsvUploadView(APIView):
    """
    Handle CSV uploads to create products in the database.
    """

    @extend_schema(
        summary="Upload products via CSV",
        description="Upload a CSV file to create product records in bulk.",
        tags=["Products"],
    )
    def post(self, request):
        csv_file = request.FILES.get("file")
        if not csv_file:
            return Response(
                {"error": "No CSV file provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            decoded_file = csv_file.read().decode("utf-8")
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)
        except Exception as e:
            return Response(
                {"error": f"Failed to read CSV file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created_products = []
        errors = []
        row_number = 1

        for row in reader:
            try:
                product = Product(
                    name=row.get("name"),
                    itemCode=row.get("itemCode") or None,
                    sku=row.get("sku") or None,
                    hsn=row.get("hsn") or None,
                    category=row.get("category") or None,
                    quantity=int(row.get("quantity", 0)),
                    itemLocation=row.get("itemLocation") or None,
                    description=row.get("description") or None,
                    price=row.get("price"),
                    msp=row.get("msp") or None,
                    mrp=row.get("mrp") or None,
                    gst=row.get("gst") or None,
                    cgst=row.get("cgst") or None,
                    sgst=row.get("sgst") or None,
                    igst=row.get("igst") or None,
                    vendorCode=row.get("vendorCode") or None,
                    vendorName=row.get("vendorName") or None,
                    purchasePrice=row.get("purchasePrice") or None,
                    purchaseLocation=row.get("purchaseLocation") or None,
                    purchaseOrderId=row.get("purchaseOrderId") or None,
                    warrantyPeriod=row.get("warrantyPeriod") or None,
                    mobis_status=row.get("mobis_status", Product.NON_MOBIS),
                )

                # Parse dates if provided (expected format: YYYY-MM-DD)
                if row.get("purchaseOrderDate"):
                    product.purchaseOrderDate = datetime.strptime(
                        row["purchaseOrderDate"], "%Y-%m-%d"
                    ).date()
                if row.get("lastUpdatedDate"):
                    product.lastUpdatedDate = datetime.strptime(
                        row["lastUpdatedDate"], "%Y-%m-%d"
                    ).date()

                product.save()
                created_products.append(str(product.id))
            except Exception as e:
                errors.append(f"Row {row_number}: {str(e)}")
            row_number += 1

        return Response(
            {"created_products": created_products, "errors": errors},
            status=status.HTTP_200_OK,
        )
