from rest_framework import serializers
from catalog.models.vehicle_models_model import VehilceModel


class VehicleModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehilceModel
        fields = [
            "id",
            "make",
            "models",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
