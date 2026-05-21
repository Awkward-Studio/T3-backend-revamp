from dataclasses import dataclass

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from jobcards.models import CurrentPart, JobCard

from .models import InventoryMovement, Product


@dataclass
class StockError(Exception):
    message: str
    status_code: int = 400


def consume_jobcard_inventory(jobcard, invoice=None):
    """
    Deduct inventory for a jobcard exactly once.

    CurrentPart is the source of truth for billable parts. JobCard.parts remains
    a legacy payload field and must not drive stock.
    """
    with transaction.atomic():
        locked_jobcard = JobCard.objects.select_for_update().get(pk=jobcard.pk)
        if locked_jobcard.inventory_consumed_at:
            return []

        current_parts = list(
            CurrentPart.objects.select_related("product")
            .filter(job_card=locked_jobcard)
            .order_by("created_at", "id")
        )

        movements = []
        for current_part in current_parts:
            if current_part.quantity <= 0:
                raise StockError(
                    f"Invalid quantity for {current_part.part_name}", status_code=400
                )

            product = Product.objects.select_for_update().get(pk=current_part.product_id)
            before_quantity = product.quantity
            if before_quantity < current_part.quantity:
                raise StockError(
                    f"Not enough stock for {product.name}. "
                    f"Available: {before_quantity}, required: {current_part.quantity}",
                    status_code=400,
                )

            updated = Product.objects.filter(
                pk=product.pk, quantity__gte=current_part.quantity
            ).update(quantity=F("quantity") - current_part.quantity)
            if updated != 1:
                raise StockError(
                    f"Stock changed while updating {product.name}. Please retry.",
                    status_code=409,
                )

            product.refresh_from_db(fields=["quantity"])
            movements.append(
                InventoryMovement.objects.create(
                    product=product,
                    job_card=locked_jobcard,
                    current_part=current_part,
                    invoice=invoice,
                    movement_type=InventoryMovement.SALE,
                    quantity=current_part.quantity,
                    quantity_delta=-current_part.quantity,
                    before_quantity=before_quantity,
                    after_quantity=product.quantity,
                    note="Consumed on final invoice",
                )
            )

        locked_jobcard.inventory_consumed_at = timezone.now()
        locked_jobcard.inventory_consumed_by = invoice
        locked_jobcard.job_card_status = 4
        locked_jobcard.save(
            update_fields=[
                "inventory_consumed_at",
                "inventory_consumed_by",
                "job_card_status",
                "updated_at",
            ]
        )

        return movements


def invoice_consumes_inventory(invoice_type):
    if not invoice_type:
        return False
    return str(invoice_type).strip().lower().replace("-", "_").replace(" ", "_") in {
        "tax_invoice",
        "tax",
    }
