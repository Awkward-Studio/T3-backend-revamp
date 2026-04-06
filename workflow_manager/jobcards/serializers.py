# yourapp/serializers.py
from rest_framework import serializers
from .models import JobCard, CurrentPart, CurrentLabour


class JobCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobCard
        fields = [
            "id",
            "car_id",  # <-- use car_id, not card_id
            "temp_car",
            "diagnosis",
            "send_to_parts_manager",
            "car_number",
            "job_card_status",
            "customer_name",
            "customer_phone",
            "customer_address",
            "customer_email",
            "gstin",
            "parts",
            "labour",
            "images",
            "job_card_number",
            "car_fuel",
            "bat_odometer",
            "insurance_details",
            "sub_total",
            "discount_amount",
            "amount",
            "taxes",
            "job_card_pdf",
            "gate_pass_pdf",
            "purpose_of_visit",
            "service_advisor_id",
            "observation_remarks",
            "calling_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "job_card_number", "created_at", "updated_at"]


class CurrentPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurrentPart
        fields = [
            "id",
            "job_card",
            "product",
            "part_id",
            "part_name",
            "part_number",
            "hsn",
            "quantity",
            "mrp",
            "discount_percentage",
            "discounted_subtotal",
            "discount_amount",
            "insurance_percentage",
            "insurance_subtotal",
            "insurance_amount",
            "sub_total",
            "total_tax",
            "amount",
            "gst",
            "cgst",
            "sgst",
            "cgst_amount",
            "sgst_amount",
            "customer_amount",
            "customer_sub_total",
            "customer_cgst_amount",
            "customer_sgst_amount",
            "customer_discount_amount",
            "customer_total_tax",
            "insurance_sub_total",
            "insurance_cgst_amount",
            "insurance_sgst_amount",
            "insurance_total_tax",
            "insurance_discount_amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CurrentLabourSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurrentLabour
        fields = [
            "id",
            "temp_car",
            "labour_id",
            "labour_name",
            "labour_code",
            "hsn_code",
            "mrp",
            "gst_percentage",
            "cgst",
            "sgst",
            "quantity",
            "sub_total",
            "cgst_amount",
            "sgst_amount",
            "total_tax",
            "total_amount",
            "discount_percentage",
            "discount_sub_total",
            "discount_amount",
            "insurance_percentage",
            "insurance_amount",
            "insurance_sub_total",
            "insurance_cgst_amount",
            "insurance_sgst_amount",
            "insurance_total_tax",
            "insurance_discount_amount",
            "customer_amount",
            "customer_sub_total",
            "customer_cgst_amount",
            "customer_sgst_amount",
            "customer_total_tax",
            "customer_discount_amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
