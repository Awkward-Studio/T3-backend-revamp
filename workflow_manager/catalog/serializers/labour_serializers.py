from rest_framework import serializers
from catalog.models.labour_models import Labour


class LabourSerializer(serializers.ModelSerializer):
    class Meta:
        model = Labour
        fields = [
            "id",
            "labour_name",
            "labour_code",
            "hsn",
            "category",
            "mrp",
            "gst",
            "cgst",
            "sgst",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
