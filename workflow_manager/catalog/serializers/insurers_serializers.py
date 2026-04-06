from rest_framework import serializers
from catalog.models.insurers_model import InsuranceProvider


class InsuranceProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuranceProvider
        fields = [
            "id",
            "insurer",
            "address",
            "gst",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
