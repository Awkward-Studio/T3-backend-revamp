import json
from decimal import Decimal, InvalidOperation

from django.db import transaction

from inventory.models import Product

from .models import CurrentPart


class JobCardPartError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _decimal(value, default=0):
    if value in (None, ""):
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _first(payload, *keys, default=None):
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _normalize_part_payload(part):
    if isinstance(part, str):
        try:
            part = json.loads(part)
        except json.JSONDecodeError:
            raise JobCardPartError("Each part must be an object")
    if not isinstance(part, dict):
        raise JobCardPartError("Each part must be an object")

    product_id = _first(part, "product_id", "product", "partId", "part_id")
    if not product_id:
        raise JobCardPartError("product_id is required for each part")

    try:
        quantity = int(_first(part, "quantity", default=1))
    except (TypeError, ValueError):
        raise JobCardPartError(f"Invalid quantity for product {product_id}")
    if quantity <= 0:
        raise JobCardPartError(
            f"Quantity must be greater than zero for product {product_id}"
        )

    return product_id, quantity


def validate_jobcard_parts_stock(parts):
    normalized = []
    for part in parts:
        if isinstance(part, str):
            try:
                part = json.loads(part)
            except json.JSONDecodeError:
                raise JobCardPartError("Each part must be an object")
        product_id, quantity = _normalize_part_payload(part)
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            raise JobCardPartError(f"Product {product_id} not found", status_code=404)
        if product.quantity < quantity:
            raise JobCardPartError(
                f"Only {product.quantity} unit(s) available for {product.name}."
            )
        normalized.append((part, product, quantity))
    return normalized


def save_jobcard_parts(jobcard, parts):
    if not isinstance(parts, list):
        raise JobCardPartError("parts must be a list")
    if jobcard.inventory_consumed_at:
        raise JobCardPartError("Cannot modify parts after inventory has been consumed.")

    prepared_parts = validate_jobcard_parts_stock(parts)
    saved = []

    with transaction.atomic():
        existing = CurrentPart.objects.filter(job_card=jobcard)
        received_product_ids = [product.id for _, product, _ in prepared_parts]
        existing.exclude(product_id__in=received_product_ids).delete()

        for payload, product, quantity in prepared_parts:
            current_part = CurrentPart.objects.filter(
                job_card=jobcard, product=product
            ).first()
            if current_part is None:
                current_part = CurrentPart(job_card=jobcard, product=product)

            current_part.part_id = str(product.id)
            current_part.part_name = product.name
            current_part.part_number = product.sku or product.itemCode or ""
            current_part.hsn = product.hsn or ""
            current_part.quantity = quantity
            current_part.mrp = _decimal(_first(payload, "mrp"), product.mrp or product.price)
            current_part.sub_total = _decimal(
                _first(payload, "sub_total", "subTotal"), current_part.mrp * quantity
            )
            current_part.total_tax = _decimal(
                _first(payload, "total_tax", "totalTax"), 0
            )
            current_part.amount = _decimal(_first(payload, "amount"), current_part.sub_total)
            current_part.gst = _decimal(_first(payload, "gst"), product.gst or 0)
            current_part.cgst = _decimal(_first(payload, "cgst"), product.cgst or 0)
            current_part.sgst = _decimal(_first(payload, "sgst"), product.sgst or 0)

            optional_fields = {
                "discount_percentage": ("discount_percentage", "discountPercentage"),
                "discounted_subtotal": ("discounted_subtotal", "discountedSubTotal"),
                "discount_amount": ("discount_amount", "discountAmt"),
                "insurance_percentage": ("insurance_percentage", "insurancePercentage"),
                "insurance_subtotal": ("insurance_subtotal", "insuranceSubtotal"),
                "insurance_amount": ("insurance_amount", "insuranceAmt"),
                "cgst_amount": ("cgst_amount", "cgstAmt"),
                "sgst_amount": ("sgst_amount", "sgstAmt"),
                "customer_amount": ("customer_amount", "customerAmt", "amountCust"),
                "customer_sub_total": ("customer_sub_total", "subTotalCust"),
                "customer_cgst_amount": ("customer_cgst_amount", "cgstAmtCust"),
                "customer_sgst_amount": ("customer_sgst_amount", "sgstAmtCust"),
                "customer_discount_amount": ("customer_discount_amount", "discountAmtCust"),
                "customer_total_tax": ("customer_total_tax", "totalTaxCust"),
                "insurance_sub_total": ("insurance_sub_total", "subTotalIns"),
                "insurance_cgst_amount": ("insurance_cgst_amount", "cgstAmtIns"),
                "insurance_sgst_amount": ("insurance_sgst_amount", "sgstAmtIns"),
                "insurance_total_tax": ("insurance_total_tax", "totalTaxIns"),
                "insurance_discount_amount": ("insurance_discount_amount", "discountAmtIns"),
            }
            for field, keys in optional_fields.items():
                value = _first(payload, *keys)
                if value is not None:
                    setattr(current_part, field, _decimal(value))

            current_part.save()
            saved.append(current_part)

    return saved
