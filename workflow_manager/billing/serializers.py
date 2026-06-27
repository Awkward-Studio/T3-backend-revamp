from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from .models import CustomerWallet, Invoice, WalletTransaction


class InvoiceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            "invoice_url",
            "is_updated",
            "invoice_code",
            "is_insurance_invoice",
            "car_number",
            "invoice_total",
            "wallet_credit_used",
            "final_amount",
            "apply_gst",
            "wallet_transaction",
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            "id",
            "job_card",
            "job_card_id",
            "car_number",
            "is_insurance_invoice",
            "invoice_series",
            "invoice_type",
            "category",
            "invoice_number",
            "invoice_code",
            "is_updated",
            "inventory_consumed_at",
            "invoice_total",
            "wallet_credit_used",
            "final_amount",
            "apply_gst",
            "wallet_transaction",
            "invoice_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "invoice_number",
            "inventory_consumed_at",
            "created_at",
            "updated_at",
        ]


class WalletTransactionSerializer(serializers.ModelSerializer):
    license_plate = serializers.CharField(
        source="wallet.car.car_number", read_only=True
    )

    class Meta:
        model = WalletTransaction
        fields = [
            "id",
            "wallet_id",
            "license_plate",
            "amount",
            "reason",
            "type",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class CustomerWalletSerializer(serializers.ModelSerializer):
    car_id = serializers.IntegerField(source="car.id", read_only=True)
    license_plate = serializers.CharField(source="car.car_number", read_only=True)
    customer_name = serializers.CharField(source="car.customer_name", read_only=True)
    vehicle_model = serializers.CharField(source="car.car_model", read_only=True)
    total_credits_issued = serializers.SerializerMethodField()

    class Meta:
        model = CustomerWallet
        fields = [
            "id",
            "car_id",
            "license_plate",
            "customer_name",
            "vehicle_model",
            "balance",
            "total_credits_issued",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_total_credits_issued(self, obj):
        annotated_value = getattr(obj, "total_credits_issued", None)
        if annotated_value is not None:
            return annotated_value

        total = obj.transactions.filter(
            type=WalletTransaction.TransactionType.CREDIT
        ).aggregate(total=Sum("amount"))["total"]
        return total or Decimal("0.00")


class AddWalletCreditSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class InvoiceWalletCreditSerializer(serializers.Serializer):
    invoice_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), required=False
    )
    wallet_credit_used = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), required=False
    )
    final_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), required=False
    )
