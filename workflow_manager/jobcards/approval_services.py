from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from jobcards.models import ApprovalItem, CustomerApproval, JobCard


class CustomerApprovalError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def get_latest_customer_approval(jobcard: JobCard) -> CustomerApproval | None:
    return jobcard.customer_approvals.order_by("-created_at").first()


def _coerce_decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _normalize_recommended_item(item, fallback_name: str = "Item") -> dict:
    if isinstance(item, str):
        name = item.strip() or fallback_name
        return {
            "name": name,
            "description": "",
            "estimated_cost": Decimal("0"),
            "image": "",
        }

    if not isinstance(item, dict):
        return {
            "name": fallback_name,
            "description": "",
            "estimated_cost": Decimal("0"),
            "image": "",
        }

    name = (
        item.get("name")
        or item.get("value")
        or item.get("labourName")
        or item.get("partName")
        or fallback_name
    )
    return {
        "name": str(name).strip() or fallback_name,
        "description": str(item.get("description") or "").strip(),
        "estimated_cost": _coerce_decimal(
            item.get("estimatedCost", item.get("estimated_cost"))
        ),
        "image": str(item.get("image") or item.get("imageURL") or "").strip(),
    }


def _build_approved_items_snapshot(items) -> list:
    return [
        {
            "type": item.item_type,
            "name": item.name,
            "description": item.description or "",
            "estimatedCost": float(item.estimated_cost or 0),
            "image": item.image or "",
            "approved": True,
        }
        for item in items
        if item.approved
    ]


def create_customer_approval(jobcard: JobCard, created_by: str = "") -> CustomerApproval:
    labour_items = jobcard.recommended_labour or []
    part_items = jobcard.recommended_parts or []

    if not labour_items and not part_items:
        raise CustomerApprovalError(
            "Add at least one suggested labour or part item before sending for approval."
        )

    pending = jobcard.customer_approvals.filter(
        status=CustomerApproval.Status.PENDING
    ).first()
    if pending:
        raise CustomerApprovalError(
            "A customer approval request is already pending.", status_code=409
        )

    with transaction.atomic():
        approval = CustomerApproval.objects.create(
            job_card=jobcard,
            created_by=created_by,
        )

        sort_order = 0
        for item in labour_items:
            normalized = _normalize_recommended_item(item, "Labour item")
            ApprovalItem.objects.create(
                customer_approval=approval,
                item_type=ApprovalItem.ItemType.LABOUR,
                name=normalized["name"],
                description=normalized["description"],
                estimated_cost=normalized["estimated_cost"],
                image=normalized["image"],
                sort_order=sort_order,
            )
            sort_order += 1

        for item in part_items:
            normalized = _normalize_recommended_item(item, "Part item")
            ApprovalItem.objects.create(
                customer_approval=approval,
                item_type=ApprovalItem.ItemType.PART,
                name=normalized["name"],
                description=normalized["description"],
                estimated_cost=normalized["estimated_cost"],
                image=normalized["image"],
                sort_order=sort_order,
            )
            sort_order += 1

        jobcard.workflow_status = JobCard.WorkflowStatus.WAITING_CUSTOMER_APPROVAL
        jobcard.save(update_fields=["workflow_status", "updated_at"])

    return approval


def submit_customer_approval(
    approval: CustomerApproval,
    item_decisions: dict,
    customer_notes: str = "",
) -> CustomerApproval:
    if approval.status != CustomerApproval.Status.PENDING:
        raise CustomerApprovalError(
            "This approval has already been submitted.", status_code=409
        )

    items = list(approval.items.all())
    if not items:
        raise CustomerApprovalError("No approval items found.")

    for item in items:
        key = str(item.id)
        if key not in item_decisions:
            raise CustomerApprovalError(
                f"Missing approval decision for: {item.name}"
            )
        decision = item_decisions[key]
        if decision is not True and decision is not False:
            raise CustomerApprovalError(
                f"Invalid approval decision for: {item.name}"
            )
        item.approved = decision
        item.save(update_fields=["approved"])

    approved_count = sum(1 for item in items if item.approved)
    rejected_count = len(items) - approved_count

    if approved_count == len(items):
        approval_status = CustomerApproval.Status.APPROVED
        workflow_status = JobCard.WorkflowStatus.CUSTOMER_APPROVED
    elif rejected_count == len(items):
        approval_status = CustomerApproval.Status.REJECTED
        workflow_status = JobCard.WorkflowStatus.CUSTOMER_REJECTED
    else:
        approval_status = CustomerApproval.Status.PARTIALLY_APPROVED
        workflow_status = JobCard.WorkflowStatus.CUSTOMER_PARTIALLY_APPROVED

    approved_items = _build_approved_items_snapshot(items)

    with transaction.atomic():
        approval.status = approval_status
        approval.customer_notes = customer_notes or ""
        approval.approved_at = timezone.now()
        approval.save(
            update_fields=["status", "customer_notes", "approved_at", "updated_at"]
        )

        jobcard = approval.job_card
        jobcard.workflow_status = workflow_status
        jobcard.approved_items = approved_items
        jobcard.save(
            update_fields=["workflow_status", "approved_items", "updated_at"]
        )

    return approval
