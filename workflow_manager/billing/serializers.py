from rest_framework import serializers
from .models import Invoice


class InvoiceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            "invoice_url",
            "is_updated",
            "invoice_code",
            "is_insurance_invoice",
            "car_number",
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
            "invoice_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "invoice_number", "created_at", "updated_at"]
