from rest_framework import serializers
from .models import InventoryMovement, Product


class ProductListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing products.
    """

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "sku",
            "hsn",
            "category",
            "quantity",
            "price",
            "description",
            "itemCode",
            "itemLocation",
            "msp",
            "mrp",
            "gst",
            "cgst",
            "sgst",
            "igst",
            "vendorName",
            "vendorCode",
            "purchasePrice",
            "purchaseLocation",
            "purchaseOrderDate",
            "purchaseOrderId",
            "warrantyPeriod",
            # "mobis_status",
            "created_at",
            "updated_at",
        ]


class ProductCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new product.
    """

    class Meta:
        model = Product
        fields = [
            "name",
            "sku",
            "hsn",
            "category",
            "quantity",
            "price",
            "description",
            "itemCode",
            "itemLocation",
            "msp",
            "mrp",
            "gst",
            "cgst",
            "sgst",
            "igst",
            "vendorCode",
            "vendorName",
            "purchasePrice",
            "purchaseLocation",
            "purchaseOrderDate",
            "purchaseOrderId",
            "warrantyPeriod",
            # "mobis_status",
            "created_at",
            "updated_at",
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for retrieving a product's details.
    """

    class Meta:
        model = Product
        fields = "__all__"


class ProductUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating a product.
    """

    class Meta:
        model = Product
        fields = [
            "name",
            "sku",
            "hsn",
            "category",
            "quantity",
            "price",
            "description",
            "itemCode",
            "itemLocation",
            "msp",
            "mrp",
            "gst",
            "cgst",
            "sgst",
            "igst",
            "vendorCode",
            "vendorName",
            "purchasePrice",
            "purchaseLocation",
            "purchaseOrderDate",
            "purchaseOrderId",
            "warrantyPeriod",
            # "mobis_status",
            "created_at",
            "updated_at",
        ]


class InventoryMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    job_card_number = serializers.IntegerField(
        source="job_card.job_card_number", read_only=True
    )
    invoice_code = serializers.CharField(source="invoice.invoice_code", read_only=True)

    class Meta:
        model = InventoryMovement
        fields = [
            "id",
            "product",
            "product_name",
            "job_card",
            "job_card_number",
            "current_part",
            "invoice",
            "invoice_code",
            "movement_type",
            "quantity",
            "quantity_delta",
            "before_quantity",
            "after_quantity",
            "note",
            "created_at",
        ]
