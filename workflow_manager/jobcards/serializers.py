import json
from decimal import Decimal

from rest_framework import serializers
from .models import JobCard, CurrentPart, CurrentLabour


class JobCardSerializer(serializers.ModelSerializer):
    """
    Output is shaped to match the Appwrite `JobCard` type from `src/lib/definitions.tsx`.
    Input validation still uses model field names (snake_case).
    """

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

    @staticmethod
    def _to_number(value):
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _parse_json_items(items):
        if not isinstance(items, list):
            return []
        parsed = []
        for item in items:
            if isinstance(item, dict):
                parsed.append(item)
                continue
            if isinstance(item, str):
                try:
                    obj = json.loads(item)
                    if isinstance(obj, dict):
                        parsed.append(obj)
                except Exception:
                    continue
        return parsed

    @classmethod
    def _sum_amount(cls, items, *possible_keys):
        total = 0.0
        for item in items:
            for key in possible_keys:
                if key in item and item[key] is not None:
                    total += cls._to_number(item[key])
                    break
        return round(total, 2)

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Parse parts/labour items (Appwrite often stores these as JSON strings)
        parts_items = self._parse_json_items(data.get("parts") or [])
        labour_items = self._parse_json_items(data.get("labour") or [])

        parts_total_pre_tax = self._sum_amount(parts_items, "subTotal", "sub_total", "subTotalCust", "sub_total_cust")
        parts_total_post_tax = self._sum_amount(parts_items, "amount", "totalAmount", "total_amount")
        labour_total_pre_tax = self._sum_amount(labour_items, "subTotal", "sub_total", "subTotalCust", "sub_total_cust")
        labour_total_post_tax = self._sum_amount(labour_items, "amount", "totalAmount", "total_amount")

        total_tax = round(
            (parts_total_post_tax - parts_total_pre_tax)
            + (labour_total_post_tax - labour_total_pre_tax),
            2,
        )

        total = round(parts_total_post_tax + labour_total_post_tax, 2)
        total_rounded = float(round(total))
        round_off_value = round(total_rounded - total, 2)

        # Build Appwrite-shaped response (camelCase + $-fields)
        out = {
            "$id": str(data.get("id")),
            "$createdAt": data.get("created_at"),
            "$updatedAt": data.get("updated_at"),
            "serviceAdvisorID": data.get("service_advisor_id"),
            "carId": data.get("car_id"),
            "diagnosis": data.get("diagnosis") or [],
            "sendToPartsManager": bool(data.get("send_to_parts_manager")),
            "carNumber": data.get("car_number"),
            "jobCardStatus": data.get("job_card_status"),
            "customerName": data.get("customer_name"),
            "customerPhone": data.get("customer_phone"),
            "customerAddress": data.get("customer_address"),
            "customerEmail": data.get("customer_email"),
            "parts": data.get("parts") or [],
            "labour": data.get("labour") or [],
            "images": data.get("images") or [],
            "observationRemarks": data.get("observation_remarks") or "",
            "partsTotalPreTax": parts_total_pre_tax,
            "partsTotalPostTax": parts_total_post_tax,
            "labourTotalPreTax": labour_total_pre_tax,
            "labourTotalPostTax": labour_total_post_tax,
            "gatePassPDF": data.get("gate_pass_pdf") or "",
            "jobCardPDF": data.get("job_card_pdf") or "",
            "subTotal": round(self._to_number(data.get("sub_total")), 2),
            "totalDiscountAmt": round(self._to_number(data.get("discount_amount")), 2),
            "amount": round(self._to_number(data.get("amount")), 2),
            "jobCardNumber": data.get("job_card_number"),
            "insuranceDetails": data.get("insurance_details") or "",
            "purposeOfVisit": data.get("purpose_of_visit") or "",
            "carFuel": data.get("car_fuel") or "",
            "carOdometer": data.get("bat_odometer") or "",
            "totalTax": total_tax,
            "gstin": data.get("gstin"),
            "placeOfSupply": data.get("place_of_supply"),
            "totalRoundedOffAmount": total_rounded,
            "roundOffValue": round_off_value,
            "taxes": data.get("taxes") or [],
        }

        # Omit optional fields when null-ish (Appwrite-style optional fields)
        for key in ("customerAddress", "customerEmail", "gstin", "placeOfSupply"):
            if out.get(key) in (None, ""):
                out.pop(key, None)

        return out


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
