# yourapp/serializers.py
from rest_framework import serializers
from .models import Car, TempCar


class CarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Car
        fields = [
            "id",
            "car_number",
            "car_make",
            "car_model",
            "location",
            "purpose_of_visit",
            "all_job_cards",
            "customer_name",
            "customer_phone",
            "customer_address",
            "purpose_of_visit_and_advisors",
            "customer_email",
            "calling_status",
        ]


class TempCarSerializer(serializers.ModelSerializer):
    # show nested Car info
    car = CarSerializer(read_only=True)
    car_id = serializers.PrimaryKeyRelatedField(
        queryset=Car.objects.all(), source="car", write_only=True
    )

    class Meta:
        model = TempCar
        fields = [
            "id",
            "car",  # read-only nested
            "car_id",  # write-only FK
            "job_card_id",
            "car_status",
            "cars_table_id",
            "purpose_of_visit_and_advisors",
            "all_job_card_ids",
        ]
