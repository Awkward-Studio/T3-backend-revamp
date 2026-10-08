from rest_framework import serializers
from .models import Car, DriverAssignment, DriverExpense, TempCar


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
            "cars_table_id",
            "customer_name",
            "customer_phone",
            "customer_address",
            "purpose_of_visit_and_advisors",
            "customer_email",
            "date_of_birth",
            "anniversary_date",
            "insurance_policy_expiry_date",
            "calling_status",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Appwrite counterpart expects `carsTableId`
        data["carsTableId"] = data.pop("cars_table_id", None)
        if data["carsTableId"] is None:
            data.pop("carsTableId", None)
        data["dateOfBirth"] = data.pop("date_of_birth", None)
        data["anniversaryDate"] = data.pop("anniversary_date", None)
        data["insurancePolicyExpiryDate"] = data.pop(
            "insurance_policy_expiry_date", None
        )
        return data


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


class DriverExpenseSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DriverExpense
        fields = [
            "id",
            "assignment",
            "category",
            "amount",
            "description",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return ""
        name = f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return name or obj.created_by.username or obj.created_by.email


class DriverAssignmentSerializer(serializers.ModelSerializer):
    driver_name = serializers.SerializerMethodField(read_only=True)
    driver_email = serializers.SerializerMethodField(read_only=True)
    driver_phone = serializers.SerializerMethodField(read_only=True)
    expenses = DriverExpenseSerializer(many=True, read_only=True)
    total_expenses = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = DriverAssignment
        fields = [
            "id",
            "assignment_type",
            "status",
            "driver",
            "driver_name",
            "driver_email",
            "driver_phone",
            "car",
            "car_number",
            "car_make",
            "car_model",
            "customer_name",
            "customer_phone",
            "customer_address",
            "customer_email",
            "temp_car",
            "job_card",
            "pickup_location",
            "drop_location",
            "notes",
            "assigned_at",
            "started_at",
            "completed_at",
            "created_by",
            "created_at",
            "updated_at",
            "expenses",
            "total_expenses",
        ]
        read_only_fields = [
            "id",
            "total_expenses",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_driver_name(self, obj):
        if not obj.driver:
            return ""
        name = f"{obj.driver.first_name} {obj.driver.last_name}".strip()
        return name or obj.driver.username or obj.driver.email

    def get_driver_email(self, obj):
        return obj.driver.email if obj.driver else ""

    def get_driver_phone(self, obj):
        if not obj.driver:
            return ""
        prefs = getattr(obj.driver, "preferences", {}) or {}
        return prefs.get("phone", "")
