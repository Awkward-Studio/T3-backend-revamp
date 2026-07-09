import json
from datetime import datetime
from decimal import Decimal

from auditlog.models import HistoryEntry
from billing.models import CustomerWallet, Invoice, WalletTransaction
from billing.services import (
    add_wallet_credit,
    apply_wallet_credit_to_invoice,
    ensure_wallet_for_car,
    get_actor_display_name,
    quantize_money,
)
from catalog.models.insurers_model import InsuranceProvider
from catalog.models.labour_models import Labour
from catalog.models.vehicle_models_model import VehilceModel
from catalog.serializers.insurers_serializers import InsuranceProviderSerializer
from django.contrib.auth import authenticate, login, logout
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import CharField, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, Replace, Upper
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from inventory.models import Product
from inventory.services import (
    StockError,
    consume_jobcard_inventory,
    invoice_consumes_inventory,
)
from jobcards.approval_services import (
    CustomerApprovalError,
    create_customer_approval,
    get_latest_customer_approval,
    submit_customer_approval,
)
from jobcards.models import ApprovalItem, CurrentPart, CustomerApproval, JobCard
from jobcards.services import JobCardPartError, save_jobcard_parts
from rest_framework import permissions, serializers, status
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from users.models import CustomUser, RoleName
from users.permissions import IsAdmin, IsBillerOnly
from users.user_management import (
    VALID_ROLE_NAMES,
    build_preferences,
    extract_advisor_roles,
    normalize_role_name,
    split_full_name,
)
from vehicle_management.models import Car, CustomerPortal, TempCar

COLLECTION_ID_MAP = {
    "66e80a830013e7a81f31": "jobcards",
    "66e933af0022ed863b96": "temp-cars",
    "66deb8920021a5819b2c": "cars",
    "66f6ce58000446f6aeaf": "parts",
    "66fa5dc6003941f79697": "labour",
    "6710ba53003b4b25a23d": "invoices",
    "678e143f003c388e2603": "vehicle-models",
    "67963228001b5bf116e6": "insurance-providers",
}

CUSTOMER_PORTAL_SESSION_KEY = "customer-portal"
POST_DELIVERY_REQUIRED_IMAGE_TYPES = [
    "Fuel",
    "Odometer",
    "Front",
    "Back",
    "Left",
    "Right",
]


def _iso(value):
    return value.isoformat() if value else None


def _doc_meta(obj, collection_id):
    return {
        "$id": str(obj.pk),
        "$createdAt": _iso(getattr(obj, "created_at", None)),
        "$updatedAt": _iso(getattr(obj, "updated_at", None)),
        "$permissions": [],
        "$databaseId": "django",
        "$collectionId": collection_id,
    }


def _list_response(items):
    return {"total": len(items), "documents": items}


def _parse_csvish_list(values):
    if values is None:
        return []
    if isinstance(values, list):
        return values
    return [values]


def _safe_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_date(value):
    if value in (None, ""):
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _iso_date(value):
    return value.isoformat() if value else None


def _parse_insurance_details_payload(raw_details):
    if raw_details in (None, ""):
        return {}, ""
    if isinstance(raw_details, dict):
        return raw_details, json.dumps(raw_details)
    if isinstance(raw_details, str):
        try:
            parsed = json.loads(raw_details)
        except json.JSONDecodeError:
            return None, None
        if not isinstance(parsed, dict):
            return None, None
        return parsed, raw_details
    return None, None


def _jobcard_vehicle_exited(jobcard):
    return (
        jobcard.workflow_status == JobCard.WorkflowStatus.VEHICLE_COLLECTED
        or int(jobcard.job_card_status or 0) >= 7
    )


def _validate_insurance_details_update(user, jobcard, raw_insurance_details):
    next_details, normalized_raw_details = _parse_insurance_details_payload(
        raw_insurance_details
    )
    if next_details is None:
        return (
            None,
            None,
            Response(
                {"error": "insuranceDetails must be a valid JSON object."},
                status=status.HTTP_400_BAD_REQUEST,
            ),
        )

    current_details, _ = _parse_insurance_details_payload(jobcard.insurance_details)
    current_details = current_details or {}

    surveyor_fields = (
        "surveyorName",
        "surveyorCompany",
        "surveyorPhoneNumber",
    )
    surveyor_details_changed = any(
        (next_details.get(field) or "") != (current_details.get(field) or "")
        for field in surveyor_fields
    )
    survey_status_changed = (next_details.get("surveyStatus") or "") != (
        current_details.get("surveyStatus") or ""
    )

    if (surveyor_details_changed or survey_status_changed) and not user.has_role(
        RoleName.BILLER
    ):
        return (
            None,
            None,
            Response(
                {
                    "error": "Only billers can update insurance surveyor details or survey status."
                },
                status=status.HTTP_403_FORBIDDEN,
            ),
        )

    if surveyor_details_changed and _jobcard_vehicle_exited(jobcard):
        return (
            None,
            None,
            Response(
                {"error": "Surveyor details cannot be edited after vehicle exit."},
                status=status.HTTP_403_FORBIDDEN,
            ),
        )

    return next_details, normalized_raw_details, None


def _json_safe(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _normalize_license_plate(value):
    return "".join(str(value or "").upper().split())


def _normalized_plate_expression(field_name):
    return Upper(Replace(field_name, Value(" "), Value(""), output_field=CharField()))


def _find_car_by_license_plate(value):
    normalized_plate = _normalize_license_plate(value)
    if not normalized_plate:
        return None
    return (
        Car.objects.annotate(
            normalized_plate=_normalized_plate_expression("car_number")
        )
        .filter(normalized_plate=normalized_plate)
        .order_by("-updated_at", "-id")
        .first()
    )


def _ensure_customer_portal(car):
    portal, _ = CustomerPortal.objects.get_or_create(car=car)
    return portal


def _customer_portal_queryset():
    return CustomerPortal.objects.select_related("car")


def _set_customer_portal_session(request, portal):
    request.session[CUSTOMER_PORTAL_SESSION_KEY] = str(portal.pk)
    request.session.set_expiry(0)
    request.session.modified = True


def _get_customer_portal_from_session(request):
    portal_id = request.session.get(CUSTOMER_PORTAL_SESSION_KEY)
    if not portal_id:
        return None
    return _customer_portal_queryset().filter(pk=portal_id).first()


def _filter_relevant_changes(data):
    excluded_fields = {
        "$collectionId",
        "$createdAt",
        "$updatedAt",
        "$id",
        "$permissions",
        "$databaseId",
    }
    return {
        key: _json_safe(value)
        for key, value in (data or {}).items()
        if key not in excluded_fields
    }


def _values_equal(left, right):
    if left == right:
        return True
    try:
        return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
    except TypeError:
        return str(left) == str(right)


def _creation_changes(data):
    return [
        {"object": key, "prevState": None, "currentState": value}
        for key, value in _filter_relevant_changes(data).items()
    ]


def _deletion_changes(data):
    return [
        {"object": key, "prevState": value, "currentState": None}
        for key, value in _filter_relevant_changes(data).items()
    ]


def _update_changes(previous, current):
    prev = _filter_relevant_changes(previous)
    curr = _filter_relevant_changes(current)
    keys = set(prev.keys()) | set(curr.keys())
    changes = []
    for key in keys:
        if not _values_equal(prev.get(key), curr.get(key)):
            changes.append(
                {
                    "object": key,
                    "prevState": prev.get(key),
                    "currentState": curr.get(key),
                }
            )
    return changes


def _history_lines(object_id, object_type, operation_type, user, changes):
    user_payload = (
        serialize_user(user) if getattr(user, "is_authenticated", False) else {}
    )
    history_entry = {
        "objectId": object_id,
        "objectType": object_type,
        "operationType": operation_type,
        "userId": user_payload.get("$id", ""),
        "userEmail": user_payload.get("email", ""),
        "userName": user_payload.get("name", ""),
        "timestamp": datetime.utcnow().isoformat(),
        "changes": changes,
    }
    return [
        f"{key}: {json.dumps(value) if isinstance(value, (list, dict)) else value}"
        for key, value in history_entry.items()
    ]


def log_history(request, object_id, object_type, operation_type, changes):
    if not changes:
        return
    user_payload = (
        serialize_user(request.user)
        if getattr(request.user, "is_authenticated", False)
        else {}
    )
    HistoryEntry.objects.create(
        object_id=str(object_id),
        object_type=object_type,
        operation_type=operation_type,
        user_id=user_payload.get("$id", ""),
        user_email=user_payload.get("email", ""),
        user_name=user_payload.get("name", ""),
        history=_history_lines(
            str(object_id), object_type, operation_type, request.user, changes
        ),
    )


def serialize_user(user):
    primary_role = user.get_primary_role()
    labels = []
    if primary_role:
        labels.append(primary_role)
    labels.extend(
        label.name
        for label in user.labels.exclude(name=primary_role)
        if label.name not in labels
    )
    full_name = f"{user.first_name} {user.last_name}".strip() or user.username
    return {
        "$id": str(user.pk),
        "$createdAt": _iso(getattr(user, "date_joined", None)),
        "$updatedAt": _iso(
            getattr(user, "last_login", None) or getattr(user, "date_joined", None)
        ),
        "name": full_name,
        "email": user.email,
        "labels": labels,
        "prefs": user.preferences or {},
        "status": bool(user.is_active),
        "currentRole": primary_role,
        "role": primary_role,
        "advisorRoles": extract_advisor_roles(user.preferences),
    }


def serialize_car(car):
    payload = {
        **_doc_meta(car, "cars"),
        "carNumber": car.car_number,
        "carMake": car.car_make,
        "carModel": car.car_model,
        "location": car.location,
        "customerName": car.customer_name,
        "customerPhone": car.customer_phone,
        "customerAddress": car.customer_address,
        "customerEmail": car.customer_email,
        "allJobCards": car.all_job_cards or [],
        "carsTableId": car.cars_table_id or str(car.pk),
        "callingStatus": car.calling_status,
        "purposeOfVisitAndAdvisors": car.purpose_of_visit_and_advisors or [],
    }
    return payload


def _is_assigned_service_advisor(user, jobcard):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.has_role(RoleName.ADMIN):
        return True
    return (jobcard.service_advisor_id or "").lower() == (user.email or "").lower()


def _can_edit_accessories(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.has_any_role((RoleName.ADMIN, RoleName.SERVICE))
    )


def _get_assigned_mechanic(jobcard):
    mechanic_id = str(jobcard.assigned_technician_id or "").strip()
    if not mechanic_id:
        return None
    try:
        mechanic_pk = int(mechanic_id)
    except (TypeError, ValueError):
        return None
    return CustomUser.objects.filter(pk=mechanic_pk).first()


def _validate_assigned_mechanic(assigned_mechanic_id):
    mechanic_id = str(assigned_mechanic_id or "").strip()
    if not mechanic_id:
        return None, None, "assignedMechanicId is required."
    try:
        mechanic_pk = int(mechanic_id)
    except (TypeError, ValueError):
        return None, None, "assignedMechanicId must be a numeric user id."

    assigned_mechanic = CustomUser.objects.filter(pk=mechanic_pk).first()
    if not assigned_mechanic or not assigned_mechanic.has_role(RoleName.MECHANIC):
        return None, None, "Assigned mechanic must be a valid mechanic user."

    return assigned_mechanic, str(mechanic_pk), None


def _serialize_assigned_mechanic(jobcard):
    mechanic = _get_assigned_mechanic(jobcard)
    return serialize_user(mechanic) if mechanic else None


def _is_assigned_mechanic(user, jobcard):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.has_role(RoleName.ADMIN):
        return True
    assigned_mechanic_id = str(jobcard.assigned_technician_id or "").strip()
    return bool(assigned_mechanic_id and assigned_mechanic_id == str(user.pk))


PARALLEL_WORKFLOW_VISIBLE_STATUSES = {
    JobCard.WorkflowStatus.CUSTOMER_APPROVED,
    JobCard.WorkflowStatus.CUSTOMER_PARTIALLY_APPROVED,
    JobCard.WorkflowStatus.MECHANIC_IN_PROGRESS,
    JobCard.WorkflowStatus.MECHANIC_COMPLETED,
    JobCard.WorkflowStatus.POST_DELIVERY_INSPECTION_PENDING,
    JobCard.WorkflowStatus.POST_DELIVERY_COMPLETED,
}


def _can_access_post_mechanic_jobcard(user, jobcard):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.has_any_role((RoleName.ADMIN, RoleName.SERVICE)):
        return True
    if user.has_role(RoleName.BILLER):
        return jobcard.workflow_status in PARALLEL_WORKFLOW_VISIBLE_STATUSES or (
            _jobcard_vehicle_exited(jobcard)
        )
    if user.has_role(RoleName.PARTS):
        return jobcard.workflow_status in PARALLEL_WORKFLOW_VISIBLE_STATUSES
    return True


def serialize_approval_item(item):
    return {
        "id": str(item.id),
        "type": item.item_type,
        "name": item.name,
        "description": item.description or "",
        "estimatedCost": float(item.estimated_cost or 0),
        "image": item.image or "",
        "approved": item.approved,
    }


def serialize_customer_approval(approval, include_job_card=False):
    items = [serialize_approval_item(item) for item in approval.items.all()]
    payload = {
        "id": str(approval.id),
        "status": approval.status,
        "customerNotes": approval.customer_notes or "",
        "approvedAt": _iso(approval.approved_at),
        "linkCreatedAt": _iso(approval.link_created_at),
        "createdBy": approval.created_by or "",
        "items": items,
        "approvalLink": "/portal",
    }
    if include_job_card:
        payload["jobCard"] = serialize_jobcard(approval.job_card)
    return payload


def _temp_car_service_actions(temp_car):
    job_card_exists = bool(temp_car.job_card_id)
    customer_approval_exists = False
    approval_link = None
    approval_status = None
    ready_for_post_delivery_inspection = False
    post_delivery_inspection_completed = False
    current_workflow_status = None

    if temp_car.job_card_id:
        jobcard = JobCard.objects.filter(pk=temp_car.job_card_id).first()
        if jobcard:
            current_workflow_status = jobcard.workflow_status
            ready_for_post_delivery_inspection = _jobcard_ready_for_post_delivery(
                jobcard
            )
            post_delivery_inspection_completed = _jobcard_post_delivery_completed(
                jobcard
            )
            approval = get_latest_customer_approval(jobcard)
            if approval:
                customer_approval_exists = True
                approval_status = approval.status
                approval_link = "/portal"

    return {
        "jobCardExists": job_card_exists,
        "customerApprovalExists": customer_approval_exists,
        "approvalLink": approval_link,
        "approvalStatus": approval_status,
        "readyForPostDeliveryInspection": ready_for_post_delivery_inspection,
        "postDeliveryInspectionCompleted": post_delivery_inspection_completed,
        "currentWorkflowStatus": current_workflow_status,
    }


def serialize_temp_car(temp_car):
    payload = {
        **_doc_meta(temp_car, "temp-cars"),
        "carNumber": temp_car.car.car_number,
        "carMake": temp_car.car.car_make,
        "carModel": temp_car.car.car_model,
        "location": temp_car.car.location,
        "purposeOfVisitAndAdvisors": temp_car.purpose_of_visit_and_advisors or [],
        "jobCardId": temp_car.job_card_id or None,
        "allJobCardIds": temp_car.all_job_card_ids or [],
        "carStatus": temp_car.car_status,
        "carsTableId": temp_car.cars_table_id or str(temp_car.car_id),
        **_temp_car_service_actions(temp_car),
    }
    return payload


def serialize_jobcard(jobcard):
    current_parts = list(jobcard.current_parts.select_related("product").all())
    parts_value = (
        [serialize_current_part(item) for item in current_parts]
        if current_parts
        else jobcard.parts or []
    )
    assigned_mechanic = _serialize_assigned_mechanic(jobcard)
    return {
        **_doc_meta(jobcard, "jobcards"),
        "serviceAdvisorID": jobcard.service_advisor_id,
        "carId": jobcard.car_id,
        "diagnosis": jobcard.diagnosis or [],
        "accessories": jobcard.accessories or [],
        "sendToPartsManager": jobcard.send_to_parts_manager,
        "carNumber": jobcard.car_number,
        "jobCardStatus": jobcard.job_card_status,
        "customerName": jobcard.customer_name,
        "customerPhone": jobcard.customer_phone,
        "customerAddress": jobcard.customer_address,
        "customerEmail": jobcard.customer_email,
        "companyName": jobcard.company_name,
        "companyPhoneNumber": jobcard.company_phone_number,
        "requiredDate": _iso_date(jobcard.required_date),
        "parts": parts_value,
        "currentParts": parts_value,
        "labour": jobcard.labour or [],
        "labourChecklist": jobcard.labour_checklist or [],
        "suggestedParts": jobcard.suggested_parts or [],
        "recommendedLabour": jobcard.recommended_labour or [],
        "recommendedParts": jobcard.recommended_parts or [],
        "advisorNotes": jobcard.advisor_notes or "",
        "workflowStatus": jobcard.workflow_status,
        "approvedItems": jobcard.approved_items or [],
        "customerApproval": (
            serialize_customer_approval(latest_approval)
            if (latest_approval := get_latest_customer_approval(jobcard))
            else None
        ),
        "images": jobcard.images or [],
        "observationRemarks": jobcard.observation_remarks or "",
        "subTotal": float(jobcard.sub_total),
        "totalDiscountAmt": float(jobcard.discount_amount),
        "amount": float(jobcard.amount),
        "jobCardNumber": jobcard.job_card_number,
        "insuranceDetails": jobcard.insurance_details or "",
        "purposeOfVisit": jobcard.purpose_of_visit or "",
        "taxes": jobcard.taxes or [],
        "applyGst": jobcard.apply_gst,
        "gatePassPDF": jobcard.gate_pass_pdf or "",
        "jobCardPDF": jobcard.job_card_pdf or "",
        "carFuel": jobcard.car_fuel or "",
        "carOdometer": jobcard.bat_odometer or "",
        "gstin": jobcard.gstin,
        "callingStatus": jobcard.calling_status,
        "inventoryConsumedAt": _iso(jobcard.inventory_consumed_at),
        "inventoryConsumedBy": str(jobcard.inventory_consumed_by_id)
        if jobcard.inventory_consumed_by_id
        else None,
        "mechanicChecklist": jobcard.mechanic_checklist or [],
        "mechanicNotes": jobcard.mechanic_notes or "",
        "postDeliveryChecklist": jobcard.post_delivery_checklist or [],
        "postDeliveryImages": jobcard.post_delivery_images or [],
        "postDeliveryCompletedAt": _iso(jobcard.post_delivery_completed_at),
        "postDeliveryCompletedBy": jobcard.post_delivery_completed_by or "",
        "assignedMechanicId": str(jobcard.assigned_technician_id or ""),
        "assignedMechanic": assigned_mechanic,
    }


def _is_mechanic(user):
    return bool(
        getattr(user, "is_authenticated", False) and user.has_role(RoleName.MECHANIC)
    )


def _get_vehicle_model(jobcard):
    temp_car = getattr(jobcard, "temp_car", None)
    car = getattr(temp_car, "car", None) if temp_car else None
    return car.car_model if car else ""


def _get_latest_approval_items(jobcard):
    approval = get_latest_customer_approval(jobcard)
    if not approval:
        return []
    return [serialize_approval_item(item) for item in approval.items.all()]


def _group_approval_items(jobcard):
    approval_items = _get_latest_approval_items(jobcard)
    approved_items = [item for item in approval_items if item.get("approved") is True]
    rejected_items = [item for item in approval_items if item.get("approved") is False]

    if not approval_items and jobcard.approved_items:
        approved_items = list(jobcard.approved_items or [])

    return {
        "approvedLabour": [
            item for item in approved_items if item.get("type") == "LABOUR"
        ],
        "rejectedLabour": [
            item for item in rejected_items if item.get("type") == "LABOUR"
        ],
        "approvedParts": [
            item for item in approved_items if item.get("type") == "PART"
        ],
        "rejectedParts": [
            item for item in rejected_items if item.get("type") == "PART"
        ],
    }


def _jobcard_ready_for_post_delivery(jobcard):
    job_card_status = int(jobcard.job_card_status or 0)
    workflow_status = jobcard.workflow_status
    return (
        job_card_status >= 5
        and not jobcard.gate_pass_pdf
        and workflow_status
        not in {
            JobCard.WorkflowStatus.POST_DELIVERY_COMPLETED,
            JobCard.WorkflowStatus.VEHICLE_COLLECTED,
        }
    )


def _jobcard_post_delivery_completed(jobcard):
    return jobcard.workflow_status in {
        JobCard.WorkflowStatus.POST_DELIVERY_COMPLETED,
        JobCard.WorkflowStatus.VEHICLE_COLLECTED,
    } or bool(jobcard.gate_pass_pdf)


def _normalize_post_delivery_task(task, index=0):
    if not isinstance(task, dict):
        task = {}

    task_name = str(task.get("name") or f"Labour task {index + 1}").strip()
    approval_item_id = str(task.get("approvalItemId") or task.get("id") or "").strip()
    task_id = str(
        task.get("id") or approval_item_id or f"post-delivery-task-{index + 1}"
    ).strip()

    return {
        "id": task_id,
        "approvalItemId": approval_item_id,
        "name": task_name,
        "completed": bool(task.get("completed", False)),
    }


def _build_post_delivery_checklist(jobcard, source_tasks=None):
    approval_groups = _group_approval_items(jobcard)
    approved_labour = approval_groups["approvedLabour"]
    existing_tasks = (
        source_tasks
        if source_tasks is not None
        else (jobcard.post_delivery_checklist or [])
    )

    normalized_tasks = [
        _normalize_post_delivery_task(task, index)
        for index, task in enumerate(existing_tasks)
    ]
    existing_by_approval_id = {
        task["approvalItemId"]: task
        for task in normalized_tasks
        if task.get("approvalItemId")
    }
    existing_by_name = {
        task["name"].strip().lower(): task
        for task in normalized_tasks
        if task.get("name")
    }

    if not approved_labour:
        return normalized_tasks, approved_labour

    checklist = []
    for index, item in enumerate(approved_labour):
        approval_item_id = str(item.get("id") or "").strip()
        task = existing_by_approval_id.get(approval_item_id) or existing_by_name.get(
            str(item.get("name") or "").strip().lower()
        )
        checklist.append(
            {
                "id": (task or {}).get("id")
                or approval_item_id
                or f"post-delivery-task-{index + 1}",
                "approvalItemId": approval_item_id,
                "name": str(item.get("name") or "Labour task").strip(),
                "completed": bool((task or {}).get("completed", False)),
            }
        )

    return checklist, approved_labour


def _normalize_post_delivery_images(images):
    return [image for image in (images or []) if isinstance(image, dict)]


def _has_all_post_delivery_images(images):
    provided_types = {
        str(image.get("imageType") or "").strip().lower()
        for image in _normalize_post_delivery_images(images)
        if image.get("imageType")
    }
    missing_types = [
        image_type
        for image_type in POST_DELIVERY_REQUIRED_IMAGE_TYPES
        if image_type.strip().lower() not in provided_types
    ]
    return len(missing_types) == 0, missing_types


def _normalize_mechanic_task(task, index=0):
    if not isinstance(task, dict):
        task = {}

    task_name = str(
        task.get("name") or task.get("labourName") or f"Task {index + 1}"
    ).strip()
    approval_item_id = str(
        task.get("approvalItemId") or task.get("approvedItemId") or ""
    ).strip()
    task_id = str(
        task.get("id") or approval_item_id or f"mechanic-task-{index + 1}"
    ).strip()

    return {
        "id": task_id,
        "approvalItemId": approval_item_id,
        "name": task_name,
        "completed": bool(task.get("completed", False)),
    }


def _build_mechanic_checklist(jobcard, source_tasks=None):
    approval_groups = _group_approval_items(jobcard)
    approved_labour = approval_groups["approvedLabour"]
    existing_tasks = (
        source_tasks if source_tasks is not None else (jobcard.mechanic_checklist or [])
    )

    normalized_tasks = [
        _normalize_mechanic_task(task, index)
        for index, task in enumerate(existing_tasks)
    ]
    existing_by_approval_id = {
        task["approvalItemId"]: task
        for task in normalized_tasks
        if task.get("approvalItemId")
    }
    existing_by_name = {
        task["name"].strip().lower(): task
        for task in normalized_tasks
        if task.get("name")
    }

    checklist = []
    for index, item in enumerate(approved_labour):
        approval_item_id = str(item.get("id") or "").strip()
        task = existing_by_approval_id.get(approval_item_id) or existing_by_name.get(
            str(item.get("name") or "").strip().lower()
        )
        checklist.append(
            {
                "id": (task or {}).get("id")
                or approval_item_id
                or f"mechanic-task-{index + 1}",
                "approvalItemId": approval_item_id,
                "name": str(item.get("name") or "Labour task").strip(),
                "completed": bool((task or {}).get("completed", False)),
            }
        )

    return checklist, approval_groups


def _mechanic_progress(checklist):
    total_tasks = len(checklist)
    completed_tasks = sum(1 for task in checklist if task.get("completed"))
    progress_percentage = (
        round((completed_tasks / total_tasks) * 100, 2) if total_tasks else 0.0
    )
    return completed_tasks, total_tasks, progress_percentage


def _jobcard_has_invoice_type(jobcard, *invoice_types):
    normalized_types = {Invoice._normalized_label(value) for value in invoice_types}
    return any(
        Invoice._normalized_label(invoice.invoice_type) in normalized_types
        for invoice in jobcard.invoices.all()
    )


def _customer_approval_status_label(approval, jobcard):
    if approval and approval.status == CustomerApproval.Status.REJECTED:
        return "Customer Rejected"
    if approval and approval.status == CustomerApproval.Status.PARTIALLY_APPROVED:
        return "Customer Partially Approved"
    if jobcard.workflow_status == JobCard.WorkflowStatus.CUSTOMER_REJECTED:
        return "Customer Rejected"
    if jobcard.workflow_status == JobCard.WorkflowStatus.CUSTOMER_PARTIALLY_APPROVED:
        return "Customer Partially Approved"
    return "Customer Approved"


def _customer_current_stage_key(approval, jobcard):
    job_card_status = int(jobcard.job_card_status or 0)

    if (
        jobcard.workflow_status == JobCard.WorkflowStatus.VEHICLE_COLLECTED
        or job_card_status >= 7
    ):
        return "VEHICLE_COLLECTED"
    if jobcard.gate_pass_pdf or job_card_status >= 6:
        return "GATE_PASS_GENERATED"
    if (
        jobcard.workflow_status == JobCard.WorkflowStatus.POST_DELIVERY_COMPLETED
        or _jobcard_ready_for_post_delivery(jobcard)
    ):
        return "POST_DELIVERY_INSPECTION"
    if job_card_status >= 1 or _jobcard_has_invoice_type(
        jobcard, "Quote", "Pro Forma Invoice", "Tax Invoice"
    ):
        return "WORKSHOP_PROCESSING"
    if jobcard.workflow_status in {
        JobCard.WorkflowStatus.CUSTOMER_APPROVED,
        JobCard.WorkflowStatus.CUSTOMER_PARTIALLY_APPROVED,
        JobCard.WorkflowStatus.MECHANIC_IN_PROGRESS,
        JobCard.WorkflowStatus.MECHANIC_COMPLETED,
    }:
        return "WORKSHOP_PROCESSING"
    return "CUSTOMER_APPROVED"


def _serialize_customer_workflow(approval, jobcard):
    current_key = _customer_current_stage_key(approval, jobcard)
    stages = [
        {
            "key": "CUSTOMER_APPROVED",
            "label": _customer_approval_status_label(approval, jobcard),
        },
        {
            "key": "WORKSHOP_PROCESSING",
            "label": "Mechanic, Parts Manager & Billing",
        },
        {"key": "POST_DELIVERY_INSPECTION", "label": "Post Delivery Inspection"},
        {"key": "GATE_PASS_GENERATED", "label": "Gate Pass Generated"},
        {"key": "VEHICLE_COLLECTED", "label": "Vehicle Collected"},
    ]
    current_index = next(
        (index for index, stage in enumerate(stages) if stage["key"] == current_key),
        0,
    )

    return {
        "currentStatus": stages[current_index]["label"],
        "progressPercentage": round(((current_index + 1) / len(stages)) * 100, 2),
        "workflowStages": [
            {
                **stage,
                "state": (
                    "completed"
                    if index < current_index
                    else "current"
                    if index == current_index
                    else "upcoming"
                ),
            }
            for index, stage in enumerate(stages)
        ],
    }


def _jobcards_for_car(car):
    base_queryset = (
        JobCard.objects.filter(temp_car__car=car)
        .select_related("temp_car", "temp_car__car")
        .prefetch_related("customer_approvals__items", "invoices")
        .distinct()
        .order_by("-created_at")
    )
    jobcards = list(base_queryset)
    if jobcards:
        return jobcards

    if not car.all_job_cards:
        return []

    fallback_jobcards = (
        JobCard.objects.filter(pk__in=car.all_job_cards)
        .select_related("temp_car", "temp_car__car")
        .prefetch_related("customer_approvals__items", "invoices")
    )
    by_id = {str(jobcard.pk): jobcard for jobcard in fallback_jobcards}
    return [
        by_id[jobcard_id]
        for jobcard_id in reversed(car.all_job_cards)
        if jobcard_id in by_id
    ]


def _current_jobcard_for_portal(jobcards):
    latest_completed_jobcard = None

    for jobcard in jobcards:
        if (
            jobcard.workflow_status != JobCard.WorkflowStatus.VEHICLE_COLLECTED
            and int(jobcard.job_card_status or 0) < 7
        ):
            return jobcard
        if latest_completed_jobcard is None:
            latest_completed_jobcard = jobcard

    return latest_completed_jobcard


def _customer_portal_can_view_post_delivery(jobcard):
    if not jobcard:
        return False

    if jobcard.workflow_status in {
        JobCard.WorkflowStatus.POST_DELIVERY_COMPLETED,
        JobCard.WorkflowStatus.VEHICLE_COLLECTED,
    }:
        return True

    return bool(jobcard.gate_pass_pdf) or int(jobcard.job_card_status or 0) >= 6


def _history_invoice_for_jobcard(jobcard):
    invoices = sorted(
        jobcard.invoices.all(), key=lambda item: item.created_at, reverse=True
    )
    if not invoices:
        return None

    for invoice in invoices:
        if Invoice._normalized_label(invoice.invoice_type) in {
            "quote",
            "pro forma invoice",
            "tax invoice",
        }:
            return invoice
    return invoices[0]


def _invoice_number_label(invoice):
    if not invoice:
        return "-"
    if invoice.invoice_code:
        return invoice.invoice_code
    series = str(invoice.invoice_series or "").upper()
    number = str(invoice.invoice_number or "").strip()
    return f"{series}-{number}".strip("-") or "-"


def _serialize_previous_visit(jobcard):
    invoice = _history_invoice_for_jobcard(jobcard)
    return {
        "jobCardId": str(jobcard.pk),
        "visitDate": _iso(jobcard.created_at),
        "invoiceNumber": _invoice_number_label(invoice),
        "purposeOfVisit": jobcard.purpose_of_visit or "-",
        "totalAmount": float(jobcard.amount or 0),
    }


def _serialize_pending_approval_for_portal(approval):
    jobcard = approval.job_card
    temp_car = jobcard.temp_car
    car = temp_car.car if temp_car else None
    payload = serialize_customer_approval(approval)
    payload.update(
        {
            "vehicle": {
                "carNumber": jobcard.car_number,
                "carMake": car.car_make if car else "",
                "carModel": car.car_model if car else "",
                "carFuel": jobcard.car_fuel or "",
                "carOdometer": jobcard.bat_odometer or "",
            },
            "vehicleNumber": jobcard.car_number,
            "vehicleModel": _get_vehicle_model(jobcard),
            "advisorNotes": jobcard.advisor_notes or "",
            "diagnosis": jobcard.diagnosis or [],
            "images": jobcard.images or [],
            "readOnly": approval.status != CustomerApproval.Status.PENDING,
        }
    )
    return payload


def _serialize_customer_portal_payload(portal):
    car = portal.car
    jobcards = _jobcards_for_car(car)
    current_jobcard = _current_jobcard_for_portal(jobcards)
    latest_approval = (
        get_latest_customer_approval(current_jobcard) if current_jobcard else None
    )
    pending_approval = (
        current_jobcard.customer_approvals.filter(
            status=CustomerApproval.Status.PENDING
        )
        .order_by("-created_at")
        .first()
        if current_jobcard
        else None
    )

    if current_jobcard:
        mechanic_checklist, _ = _build_mechanic_checklist(current_jobcard)
        post_delivery_checklist, _ = _build_post_delivery_checklist(current_jobcard)
        post_delivery_visible = _customer_portal_can_view_post_delivery(current_jobcard)
        post_delivery_images = _normalize_post_delivery_images(
            current_jobcard.post_delivery_images
        )
        completed_task_count, total_task_count, mechanic_progress_percentage = (
            _mechanic_progress(mechanic_checklist)
        )
        workflow_payload = _serialize_customer_workflow(
            pending_approval or latest_approval, current_jobcard
        )
        current_vehicle_status = {
            "hasActiveVisit": True,
            "jobCardId": str(current_jobcard.pk),
            "purposeOfVisit": current_jobcard.purpose_of_visit or "-",
            "visitDate": _iso(current_jobcard.created_at),
            "currentStatus": workflow_payload["currentStatus"],
            "progressPercentage": workflow_payload["progressPercentage"],
            "workflowStages": workflow_payload["workflowStages"],
            "mechanicChecklist": mechanic_checklist,
            "accessories": current_jobcard.accessories or [],
            "completedTaskCount": completed_task_count,
            "totalTaskCount": total_task_count,
            "mechanicProgressPercentage": mechanic_progress_percentage,
            "postDeliveryInspectionVisible": post_delivery_visible,
            "postDeliveryChecklist": (
                post_delivery_checklist if post_delivery_visible else []
            ),
            "postDeliveryImages": post_delivery_images if post_delivery_visible else [],
            "postDeliveryRequiredImageTypes": (
                POST_DELIVERY_REQUIRED_IMAGE_TYPES if post_delivery_visible else []
            ),
            "postDeliveryCompletedAt": (
                _iso(current_jobcard.post_delivery_completed_at)
                if post_delivery_visible
                else None
            ),
            "postDeliveryCompletedBy": (
                current_jobcard.post_delivery_completed_by or ""
                if post_delivery_visible
                else ""
            ),
        }
    else:
        current_vehicle_status = {
            "hasActiveVisit": False,
            "jobCardId": None,
            "purposeOfVisit": "-",
            "visitDate": None,
            "currentStatus": "No Active Visit",
            "progressPercentage": 0,
            "workflowStages": [],
            "mechanicChecklist": [],
            "accessories": [],
            "completedTaskCount": 0,
            "totalTaskCount": 0,
            "mechanicProgressPercentage": 0,
            "postDeliveryInspectionVisible": False,
            "postDeliveryChecklist": [],
            "postDeliveryImages": [],
            "postDeliveryRequiredImageTypes": [],
            "postDeliveryCompletedAt": None,
            "postDeliveryCompletedBy": "",
        }

    previous_visits = [
        _serialize_previous_visit(jobcard)
        for jobcard in jobcards
        if not current_jobcard or jobcard.pk != current_jobcard.pk
    ]
    wallet = ensure_wallet_for_car(car)
    wallet_transactions = wallet.transactions.order_by("-created_at", "-id")[:5]
    wallet_history = [
        {
            "id": transaction_row.pk,
            "date": _iso(transaction_row.created_at),
            "amount": float(transaction_row.amount or 0),
            "reason": transaction_row.reason,
            "type": transaction_row.type,
        }
        for transaction_row in wallet_transactions
    ]

    return {
        "authenticated": True,
        "portal": {
            "id": str(portal.pk),
            "carId": str(car.pk),
        },
        "vehicle": {
            "carNumber": car.car_number,
            "carMake": car.car_make,
            "carModel": car.car_model,
            "carFuel": current_jobcard.car_fuel if current_jobcard else "",
            "carOdometer": current_jobcard.bat_odometer if current_jobcard else "",
        },
        "vehicleNumber": car.car_number,
        "vehicleModel": car.car_model,
        "currentVehicleStatus": current_vehicle_status,
        "pendingApproval": (
            _serialize_pending_approval_for_portal(pending_approval)
            if pending_approval
            else None
        ),
        "pendingApprovalsCount": 1 if pending_approval else 0,
        "walletBalance": {
            "enabled": True,
            "amount": float(wallet.balance or 0),
            "label": "Wallet Balance",
            "transactions": wallet_history,
        },
        "previousVisits": previous_visits,
    }


def serialize_mechanic_jobcard(jobcard):
    checklist, approval_groups = _build_mechanic_checklist(jobcard)
    completed_task_count, total_task_count, progress_percentage = _mechanic_progress(
        checklist
    )

    return {
        **serialize_jobcard(jobcard),
        "vehicleModel": _get_vehicle_model(jobcard),
        "approvedLabour": approval_groups["approvedLabour"],
        "rejectedLabour": approval_groups["rejectedLabour"],
        "approvedParts": approval_groups["approvedParts"],
        "rejectedParts": approval_groups["rejectedParts"],
        "mechanicChecklist": checklist,
        "mechanicNotes": jobcard.mechanic_notes or "",
        "completedTaskCount": completed_task_count,
        "totalTaskCount": total_task_count,
        "progressPercentage": progress_percentage,
        "readOnly": jobcard.workflow_status
        == JobCard.WorkflowStatus.MECHANIC_COMPLETED,
    }


def serialize_post_delivery_jobcard(jobcard):
    checklist, approved_labour = _build_post_delivery_checklist(jobcard)
    all_checked = (
        all(task.get("completed") for task in checklist) if checklist else True
    )
    has_all_images, missing_image_types = _has_all_post_delivery_images(
        jobcard.post_delivery_images
    )

    return {
        **serialize_jobcard(jobcard),
        "vehicleModel": _get_vehicle_model(jobcard),
        "approvedLabour": approved_labour,
        "postDeliveryChecklist": checklist,
        "postDeliveryImages": jobcard.post_delivery_images or [],
        "postDeliveryRequiredImageTypes": POST_DELIVERY_REQUIRED_IMAGE_TYPES,
        "readyForPostDeliveryInspection": _jobcard_ready_for_post_delivery(jobcard),
        "postDeliveryInspectionCompleted": _jobcard_post_delivery_completed(jobcard),
        "allChecklistItemsCompleted": all_checked,
        "allPostDeliveryImagesUploaded": has_all_images,
        "missingPostDeliveryImageTypes": missing_image_types,
        "readOnly": _jobcard_post_delivery_completed(jobcard),
    }


def serialize_product(product):
    return {
        **_doc_meta(product, "parts"),
        "partName": product.name,
        "partNumber": product.sku or product.itemCode or "",
        "hsn": product.hsn or "",
        "category": product.category or "",
        "mrp": float(product.mrp or product.price or 0),
        "gst": float(product.gst or 0),
        "cgst": float(product.cgst or 0),
        "sgst": float(product.sgst or 0),
        "quantity": product.quantity,
        "itemCode": product.itemCode,
        "itemLocation": product.itemLocation,
        "vendorName": product.vendorName,
    }


def serialize_current_part(current_part):
    product_quantity = getattr(current_part.product, "quantity", None)
    return {
        "$id": str(current_part.id),
        "partId": str(current_part.product_id),
        "partName": current_part.part_name,
        "partNumber": current_part.part_number,
        "mrp": float(current_part.mrp or 0),
        "gst": float(current_part.gst or 0),
        "hsn": current_part.hsn or "",
        "cgst": float(current_part.cgst or 0),
        "sgst": float(current_part.sgst or 0),
        "quantity": current_part.quantity,
        "availableStock": product_quantity,
        "subTotal": float(current_part.sub_total or 0),
        "cgstAmt": float(current_part.cgst_amount or 0),
        "sgstAmt": float(current_part.sgst_amount or 0),
        "totalTax": float(current_part.total_tax or 0),
        "amount": float(current_part.amount or 0),
        "discountPercentage": float(current_part.discount_percentage or 0),
        "discountedSubTotal": float(current_part.discounted_subtotal or 0),
        "discountAmt": float(current_part.discount_amount or 0),
        "insurancePercentage": float(current_part.insurance_percentage or 0),
        "insuranceAmt": float(current_part.insurance_amount or 0),
        "customerAmt": float(current_part.customer_amount or 0),
        "amountCust": float(current_part.customer_amount or 0),
        "subTotalCust": float(current_part.customer_sub_total or 0),
        "cgstAmtCust": float(current_part.customer_cgst_amount or 0),
        "sgstAmtCust": float(current_part.customer_sgst_amount or 0),
        "discountAmtCust": float(current_part.customer_discount_amount or 0),
        "totalTaxCust": float(current_part.customer_total_tax or 0),
        "amountIns": float(current_part.insurance_amount or 0),
        "subTotalIns": float(current_part.insurance_sub_total or 0),
        "cgstAmtIns": float(current_part.insurance_cgst_amount or 0),
        "sgstAmtIns": float(current_part.insurance_sgst_amount or 0),
        "totalTaxIns": float(current_part.insurance_total_tax or 0),
        "discountAmtIns": float(current_part.insurance_discount_amount or 0),
    }


def serialize_labour(labour):
    return {
        **_doc_meta(labour, "labour"),
        "labourName": labour.labour_name,
        "labourCode": labour.labour_code,
        "hsn": labour.hsn,
        "category": labour.category or "",
        "mrp": float(labour.mrp),
        "gst": float(labour.gst or 0),
        "cgst": float(labour.cgst or 0),
        "sgst": float(labour.sgst or 0),
    }


def serialize_invoice(invoice):
    return {
        **_doc_meta(invoice, "invoices"),
        "invoiceUrl": invoice.invoice_url,
        "jobCardId": str(invoice.job_card_id),
        "carNumber": invoice.car_number,
        "invoiceType": invoice.invoice_type,
        "invoiceNumber": invoice.invoice_number,
        "invoiceSeries": invoice.invoice_series,
        "invoiceCode": invoice.invoice_code,
        "isUpdatedInvoice": invoice.is_updated,
        "insuranceInvoiceType": invoice.category,
        "isInsuranceInvoice": invoice.is_insurance_invoice,
        "invoiceTotal": float(invoice.invoice_total or 0),
        "walletCreditUsed": float(invoice.wallet_credit_used or 0),
        "finalAmount": float(invoice.final_amount or 0),
        "applyGst": invoice.apply_gst,
        "walletTransactionId": invoice.wallet_transaction_id,
        "invoiceDate": _iso(invoice.created_at),
    }


class _InvoiceFinancialsSerializer(serializers.Serializer):
    invoiceTotal = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), required=False
    )
    walletCreditUsed = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), required=False
    )
    finalAmount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), required=False
    )


def _extract_invoice_financials(data):
    serializer = _InvoiceFinancialsSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    invoice_total = quantize_money(serializer.validated_data.get("invoiceTotal"))
    wallet_credit_used = quantize_money(
        serializer.validated_data.get("walletCreditUsed")
    )
    final_amount = quantize_money(serializer.validated_data.get("finalAmount"))

    if wallet_credit_used > invoice_total:
        raise ValueError("Credit amount cannot exceed invoice total.")

    expected_final_amount = quantize_money(invoice_total - wallet_credit_used)
    if final_amount in {Decimal("0.00"), expected_final_amount}:
        final_amount = expected_final_amount
    else:
        raise ValueError("Final amount must equal invoice total minus credits used.")

    return invoice_total, wallet_credit_used, final_amount


def serialize_vehicle_model(item):
    return {
        **_doc_meta(item, "vehicle-models"),
        "make": item.make,
        "models": item.models or [],
    }


def serialize_insurance_provider(item):
    return {
        **_doc_meta(item, "insurance-providers"),
        "insurer": item.insurer,
        "address": item.address,
        "GST": item.gst,
    }


def _normalize_insurance_provider_payload(data):
    payload = dict(data or {})
    if "GST" in payload and "gst" not in payload:
        payload["gst"] = payload["GST"]
    payload.pop("GST", None)
    payload.pop("$id", None)
    payload.pop("$createdAt", None)
    payload.pop("$updatedAt", None)
    payload.pop("$permissions", None)
    payload.pop("$databaseId", None)
    payload.pop("$collectionId", None)
    return payload


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return


class CompatSchemaSerializer(serializers.Serializer):
    pass


@method_decorator(csrf_exempt, name="dispatch")
class CompatAPIView(GenericAPIView):
    authentication_classes = [CsrfExemptSessionAuthentication, BasicAuthentication]
    serializer_class = CompatSchemaSerializer


class CompatAuthLoginView(CompatAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password", "")
        user = authenticate(request, username=email, password=password)
        if not user:
            user = CustomUser.objects.filter(email__iexact=email).first()
            if user and user.check_password(password):
                login(request, user)
                return Response(
                    {
                        "userDetails": serialize_user(user),
                        "sessionDetails": {
                            "$id": request.session.session_key or "current"
                        },
                    }
                )
            return Response(
                {"errorMsg": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )

        login(request, user)
        return Response(
            {
                "userDetails": serialize_user(user),
                "sessionDetails": {"$id": request.session.session_key or "current"},
            }
        )


class CompatAuthLogoutView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"success": True})


class CompatAuthMeView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(serialize_user(request.user))

    def patch(self, request):
        user = request.user
        if "name" in request.data:
            name = request.data.get("name", "").strip()
            if " " in name:
                first, last = name.split(" ", 1)
            else:
                first, last = name, ""
            user.first_name = first
            user.last_name = last
        if "email" in request.data:
            user.email = request.data["email"]
            if not user.username:
                user.username = request.data["email"]
        if "prefs" in request.data:
            user.preferences = request.data["prefs"]
        if "password" in request.data:
            user.set_password(request.data["password"])
        user.save()
        return Response(serialize_user(user), status=status.HTTP_200_OK)


class CompatCurrentUserSessionsView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            {"sessions": [{"$id": request.session.session_key or "current"}]}
        )


def _compat_is_admin(request):
    return bool(
        getattr(request.user, "is_authenticated", False)
    ) and request.user.has_role(RoleName.ADMIN)


class CompatUserListView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = CustomUser.objects.all().order_by("id")
        role = normalize_role_name(request.query_params.get("role"))
        if role:
            qs = qs.filter(roles__name=role).distinct()
        users = [serialize_user(user) for user in qs]
        return Response(users)

    def post(self, request):
        if not _compat_is_admin(request):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password", "")
        name = request.data.get("name", "").strip()
        role = normalize_role_name(request.data.get("role"))
        prefs = request.data.get("prefs", request.data.get("preferences"))
        advisor_roles = request.data.get(
            "advisorRoles", request.data.get("advisor_roles")
        )

        if not email:
            return Response(
                {"error": "email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not password:
            return Response(
                {"error": "password is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not role:
            return Response(
                {"error": "role is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if role not in VALID_ROLE_NAMES:
            return Response(
                {"error": "invalid role"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if CustomUser.objects.filter(email__iexact=email).exists():
            return Response(
                {"error": "A user with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            preferences = build_preferences(
                None,
                role_name=role,
                advisor_roles=advisor_roles,
                prefs_payload=prefs,
                advisor_roles_provided=advisor_roles is not None,
            )
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        first_name, last_name = split_full_name(name)

        user = CustomUser.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            preferences=preferences,
        )
        user.set_single_role(role)
        return Response(serialize_user(user), status=status.HTTP_201_CREATED)


class CompatUserDetailView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(CustomUser, pk=pk)

    def get(self, request, pk):
        return Response(serialize_user(self.get_object(pk)))

    def patch(self, request, pk):
        if not _compat_is_admin(request):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        user = self.get_object(pk)
        email = request.data.get("email")
        role = request.data.get("role")
        name = request.data.get("name")
        prefs = request.data.get("prefs", request.data.get("preferences"))
        password = request.data.get("password")
        advisor_roles_provided = (
            "advisorRoles" in request.data or "advisor_roles" in request.data
        )
        advisor_roles = request.data.get(
            "advisorRoles", request.data.get("advisor_roles")
        )

        if email is not None:
            email = str(email).strip().lower()
            if not email:
                return Response(
                    {"error": "email is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if (
                CustomUser.objects.filter(email__iexact=email)
                .exclude(pk=user.pk)
                .exists()
            ):
                return Response(
                    {"error": "A user with this email already exists."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.email = email
            user.username = email

        if role is not None:
            role = normalize_role_name(role)
            if role not in VALID_ROLE_NAMES:
                return Response(
                    {"error": "invalid role"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.set_single_role(role)
        else:
            role = user.get_primary_role()

        if name is not None:
            first_name, last_name = split_full_name(name)
            user.first_name = first_name
            user.last_name = last_name

        try:
            user.preferences = build_preferences(
                user.preferences,
                role_name=role,
                advisor_roles=advisor_roles,
                prefs_payload=prefs,
                advisor_roles_provided=advisor_roles_provided,
            )
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if password:
            user.set_password(password)

        user.save()
        return Response(serialize_user(user), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        if not _compat_is_admin(request):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        user = self.get_object(pk)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompatHistoryView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="List history entries",
        description="Returns Appwrite-like history documents used by the admin change log.",
        tags=["History"],
        responses={200: OpenApiResponse(description="History list")},
    )
    def get(self, request):
        limit = int(request.query_params.get("limit", 100))
        offset = int(request.query_params.get("offset", 0))
        entries = HistoryEntry.objects.all()[offset : offset + limit]
        documents = [
            {
                "$id": str(entry.id),
                "$createdAt": _iso(entry.created_at),
                "$updatedAt": _iso(entry.created_at),
                "$permissions": [],
                "$databaseId": "django",
                "$collectionId": "history",
                "history": entry.history,
            }
            for entry in entries
        ]
        return Response(_list_response(documents))


class CompatDocumentsByIdsView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Resolve documents by ids",
        description="Batch lookup for migrated collection ids used by the admin history screen.",
        tags=["History"],
        responses={200: OpenApiResponse(description="Resolved documents")},
    )
    def post(self, request):
        collection_id = request.data.get("collectionId")
        ids = request.data.get("ids", [])
        collection_name = COLLECTION_ID_MAP.get(collection_id)
        if not collection_name:
            return Response([], status=status.HTTP_200_OK)

        serializers = {
            "jobcards": lambda qs: [serialize_jobcard(item) for item in qs],
            "temp-cars": lambda qs: [
                serialize_temp_car(item) for item in qs.select_related("car")
            ],
            "cars": lambda qs: [serialize_car(item) for item in qs],
            "parts": lambda qs: [serialize_product(item) for item in qs],
            "labour": lambda qs: [serialize_labour(item) for item in qs],
            "invoices": lambda qs: [serialize_invoice(item) for item in qs],
            "vehicle-models": lambda qs: [serialize_vehicle_model(item) for item in qs],
            "insurance-providers": lambda qs: [
                serialize_insurance_provider(item) for item in qs
            ],
        }
        querysets = {
            "jobcards": JobCard.objects.filter(pk__in=ids),
            "temp-cars": TempCar.objects.filter(pk__in=ids),
            "cars": Car.objects.filter(pk__in=ids),
            "parts": Product.objects.filter(pk__in=ids),
            "labour": Labour.objects.filter(pk__in=ids),
            "invoices": Invoice.objects.filter(pk__in=ids),
            "vehicle-models": VehilceModel.objects.filter(pk__in=ids),
            "insurance-providers": InsuranceProvider.objects.filter(pk__in=ids),
        }
        return Response(
            serializers[collection_name](querysets[collection_name]),
            status=status.HTTP_200_OK,
        )


class CompatCarsView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cars = Car.objects.all().order_by("-id")
        updated_before = _safe_dt(request.query_params.get("updated_before"))
        if updated_before:
            cars = cars.filter(updated_at__lte=updated_before)
        return Response(_list_response([serialize_car(car) for car in cars]))

    def post(self, request):
        submitted_plate = request.data.get("carNumber", "")
        normalized_plate = _normalize_license_plate(submitted_plate)
        if not normalized_plate:
            return Response(
                {"error": "Car number is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_car = _find_car_by_license_plate(submitted_plate)
        if existing_car:
            previous = serialize_car(existing_car)
            field_map = {
                "carMake": "car_make",
                "carModel": "car_model",
                "location": "location",
                "purposeOfVisitAndAdvisors": "purpose_of_visit_and_advisors",
                "dateOfBirth": "date_of_birth",
                "anniversaryDate": "anniversary_date",
                "insurancePolicyExpiryDate": "insurance_policy_expiry_date",
            }
            updated_fields = []
            for source, target in field_map.items():
                if source in request.data:
                    setattr(existing_car, target, request.data.get(source))
                    updated_fields.append(target)
            _ensure_customer_portal(existing_car)
            if updated_fields:
                if "updated_at" not in updated_fields:
                    updated_fields.append("updated_at")
                existing_car.save(update_fields=updated_fields)
                log_history(
                    request,
                    existing_car.pk,
                    "cars",
                    "updated",
                    _update_changes(previous, serialize_car(existing_car)),
                )
            return Response(serialize_car(existing_car), status=status.HTTP_200_OK)

        car = Car.objects.create(
            car_number=normalized_plate,
            car_make=request.data.get("carMake", ""),
            car_model=request.data.get("carModel", ""),
            location=request.data.get("location", ""),
            purpose_of_visit_and_advisors=request.data.get(
                "purposeOfVisitAndAdvisors", []
            ),
            date_of_birth=request.data.get("dateOfBirth") or None,
            anniversary_date=request.data.get("anniversaryDate") or None,
            insurance_policy_expiry_date=request.data.get("insurancePolicyExpiryDate")
            or None,
        )
        car.cars_table_id = str(car.pk)
        car.save(update_fields=["cars_table_id"])
        _ensure_customer_portal(car)
        log_history(
            request, car.pk, "cars", "created", _creation_changes(serialize_car(car))
        )
        return Response(serialize_car(car), status=status.HTTP_201_CREATED)


class CompatCarSearchView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        car_number = request.query_params.get("carNumber")
        term = request.query_params.get("q")
        qs = (
            Car.objects.all()
            .annotate(normalized_plate=_normalized_plate_expression("car_number"))
            .order_by("-id")
        )
        if car_number:
            qs = qs.filter(normalized_plate=_normalize_license_plate(car_number))
        elif term:
            normalized_term = _normalize_license_plate(term)
            if normalized_term:
                qs = qs.filter(normalized_plate__icontains=normalized_term)
            else:
                qs = qs.filter(car_number__icontains=term)
        return Response(_list_response([serialize_car(car) for car in qs]))


class CompatCarDetailView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        car = get_object_or_404(Car, pk=pk)
        return Response(serialize_car(car))

    def patch(self, request, pk):
        car = get_object_or_404(Car, pk=pk)
        previous = serialize_car(car)
        field_map = {
            "carNumber": "car_number",
            "carMake": "car_make",
            "carModel": "car_model",
            "location": "location",
            "customerName": "customer_name",
            "customerPhone": "customer_phone",
            "customerAddress": "customer_address",
            "customerEmail": "customer_email",
            "allJobCards": "all_job_cards",
            "carsTableId": "cars_table_id",
            "callingStatus": "calling_status",
            "purposeOfVisitAndAdvisors": "purpose_of_visit_and_advisors",
        }
        updated_fields = []
        for source, target in field_map.items():
            if source in request.data:
                setattr(car, target, request.data[source])
                updated_fields.append(target)
        if updated_fields:
            if "updated_at" not in updated_fields:
                updated_fields.append("updated_at")
            car.save(update_fields=updated_fields)
            log_history(
                request,
                car.pk,
                "cars",
                "updated",
                _update_changes(previous, serialize_car(car)),
            )
        return Response(serialize_car(car))


class CompatTempCarsView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = TempCar.objects.select_related("car").all().order_by("-id")
        statuses = _parse_csvish_list(request.query_params.getlist("statuses"))
        if statuses:
            qs = qs.filter(car_status__in=statuses)
        term = request.query_params.get("q")
        if term:
            qs = qs.filter(car__car_number__icontains=term)
        return Response(_list_response([serialize_temp_car(item) for item in qs]))

    def post(self, request):
        car = get_object_or_404(Car, pk=request.data.get("carsTableId"))
        _ensure_customer_portal(car)
        # Keep temp-car history pointers in sync with the parent car unless explicitly provided.
        all_job_card_ids = request.data.get("allJobCardIds")
        if all_job_card_ids is None:
            all_job_card_ids = car.all_job_cards or []
        temp_car = TempCar.objects.create(
            car=car,
            car_status=request.data.get("carStatus", 0),
            cars_table_id=request.data.get("carsTableId", str(car.pk)),
            purpose_of_visit_and_advisors=request.data.get(
                "purposeOfVisitAndAdvisors", []
            ),
            all_job_card_ids=all_job_card_ids,
            job_card_id=request.data.get("jobCardId", ""),
        )
        log_history(
            request,
            temp_car.pk,
            "temp-cars",
            "created",
            _creation_changes(serialize_temp_car(temp_car)),
        )
        return Response(serialize_temp_car(temp_car), status=status.HTTP_201_CREATED)


class CompatTempCarDetailView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        temp_car = get_object_or_404(TempCar.objects.select_related("car"), pk=pk)
        return Response(serialize_temp_car(temp_car))

    def patch(self, request, pk):
        temp_car = get_object_or_404(TempCar, pk=pk)
        previous = serialize_temp_car(temp_car)
        field_map = {
            "jobCardId": "job_card_id",
            "carStatus": "car_status",
            "carsTableId": "cars_table_id",
            "purposeOfVisitAndAdvisors": "purpose_of_visit_and_advisors",
            "allJobCardIds": "all_job_card_ids",
        }
        updated_fields = []
        for source, target in field_map.items():
            if source in request.data:
                setattr(temp_car, target, request.data[source])
                updated_fields.append(target)
        if updated_fields:
            temp_car.save(update_fields=updated_fields)
            log_history(
                request,
                temp_car.pk,
                "temp-cars",
                "updated",
                _update_changes(previous, serialize_temp_car(temp_car)),
            )
        return Response(serialize_temp_car(temp_car))

    def delete(self, request, pk):
        temp_car = get_object_or_404(TempCar, pk=pk)
        previous = serialize_temp_car(temp_car)
        temp_car.delete()
        log_history(request, pk, "temp-cars", "deleted", _deletion_changes(previous))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompatJobCardsView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = JobCard.objects.all().order_by("-created_at")

        if request.user.has_role(RoleName.MECHANIC):
            qs = qs.filter(assigned_technician_id=str(request.user.pk))
        elif request.user.has_any_role(
            (RoleName.PARTS, RoleName.BILLER)
        ) and not request.user.has_any_role((RoleName.ADMIN, RoleName.SERVICE)):
            qs = qs.filter(workflow_status__in=PARALLEL_WORKFLOW_VISIBLE_STATUSES)

        statuses = _parse_csvish_list(request.query_params.getlist("statuses"))
        if statuses:
            qs = qs.filter(job_card_status__in=statuses)
        workflow_statuses = _parse_csvish_list(
            request.query_params.getlist("workflowStatuses")
        )
        if workflow_statuses:
            qs = qs.filter(workflow_status__in=workflow_statuses)
        created_gte = _safe_dt(request.query_params.get("created_gte"))
        created_lte = _safe_dt(request.query_params.get("created_lte"))
        if created_gte:
            qs = qs.filter(created_at__gte=created_gte)
        if created_lte:
            qs = qs.filter(created_at__lte=created_lte)
        return Response(_list_response([serialize_jobcard(jobcard) for jobcard in qs]))

    def post(self, request):
        if not request.user.has_any_role((RoleName.SERVICE, RoleName.ADMIN)):
            return Response(
                {"error": "Only service advisors can create job cards."},
                status=status.HTTP_403_FORBIDDEN,
            )

        _, assigned_mechanic_id, assigned_mechanic_error = _validate_assigned_mechanic(
            request.data.get("assignedMechanicId")
        )
        if assigned_mechanic_error:
            return Response(
                {"error": assigned_mechanic_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        required_date_raw = request.data.get("requiredDate")
        if required_date_raw in (None, ""):
            return Response(
                {"error": "requiredDate is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        required_date = _safe_date(required_date_raw)
        if not required_date:
            return Response(
                {"error": "requiredDate must be a valid date in YYYY-MM-DD format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        temp_car = get_object_or_404(
            TempCar.objects.select_related("car"), pk=request.data.get("carId")
        )
        jobcard_defaults = {
            "temp_car": temp_car,
            "diagnosis": request.data.get("diagnosis", []),
            "accessories": request.data.get("accessories", []),
            "send_to_parts_manager": request.data.get("sendToPartsManager", False),
            "car_number": request.data.get("carNumber", temp_car.car.car_number),
            "job_card_status": request.data.get("jobCardStatus", 0),
            "customer_name": request.data.get("customerName", ""),
            "customer_phone": request.data.get("customerPhone", ""),
            "customer_address": request.data.get("customerAddress", ""),
            "customer_email": request.data.get("customerEmail", ""),
            "company_name": request.data.get("companyName", ""),
            "company_phone_number": request.data.get("companyPhoneNumber", ""),
            "required_date": required_date,
            "date_of_birth": request.data.get("dateOfBirth") or None,
            "anniversary_date": request.data.get("anniversaryDate") or None,
            "insurance_policy_expiry_date": request.data.get(
                "insurancePolicyExpiryDate"
            )
            or None,
            "images": request.data.get("images", []),
            "labour_checklist": request.data.get("labourChecklist", []),
            "suggested_parts": request.data.get("suggestedParts", []),
            "recommended_labour": request.data.get("recommendedLabour", []),
            "recommended_parts": request.data.get("recommendedParts", []),
            "advisor_notes": request.data.get("advisorNotes", ""),
            "workflow_status": request.data.get(
                "workflowStatus", JobCard.WorkflowStatus.JOB_CARD_CREATED
            ),
            "car_fuel": request.data.get("carFuel", ""),
            "bat_odometer": request.data.get("carOdometer", ""),
            "purpose_of_visit": request.data.get("purposeOfVisit", ""),
            "job_card_pdf": request.data.get("jobCardPDF", ""),
            "apply_gst": bool(request.data.get("applyGst", True)),
            "service_advisor_id": request.data.get("serviceAdvisorID", ""),
            "assigned_technician_id": assigned_mechanic_id,
        }
        jobcard, created = JobCard.objects.get_or_create(
            car_id=str(temp_car.pk),
            defaults=jobcard_defaults,
        )

        if not created:
            update_fields = []
            if jobcard.assigned_technician_id != assigned_mechanic_id:
                jobcard.assigned_technician_id = assigned_mechanic_id
                update_fields.append("assigned_technician_id")
            if jobcard.required_date != required_date:
                jobcard.required_date = required_date
                update_fields.append("required_date")
            if update_fields:
                jobcard.save(update_fields=[*update_fields, "updated_at"])

            temp_car.car_status = 1
            temp_car.job_card_id = str(jobcard.pk)
            if str(jobcard.pk) not in temp_car.all_job_card_ids:
                temp_car.all_job_card_ids = [
                    *temp_car.all_job_card_ids,
                    str(jobcard.pk),
                ]
            temp_car.save(
                update_fields=["car_status", "job_card_id", "all_job_card_ids"]
            )

            car = temp_car.car
            if str(jobcard.pk) not in car.all_job_cards:
                car.all_job_cards = [*car.all_job_cards, str(jobcard.pk)]
            car.customer_name = jobcard.customer_name
            car.customer_phone = jobcard.customer_phone
            car.customer_address = jobcard.customer_address or ""
            car.customer_email = jobcard.customer_email or ""
            car.save(
                update_fields=[
                    "all_job_cards",
                    "customer_name",
                    "customer_phone",
                    "customer_address",
                    "customer_email",
                ]
            )
            return Response(serialize_jobcard(jobcard), status=status.HTTP_200_OK)

        temp_car.car_status = 1
        temp_car.job_card_id = str(jobcard.pk)
        temp_car.all_job_card_ids = [*temp_car.all_job_card_ids, str(jobcard.pk)]
        temp_car.save(update_fields=["car_status", "job_card_id", "all_job_card_ids"])

        car = temp_car.car
        car.all_job_cards = [*car.all_job_cards, str(jobcard.pk)]
        car.customer_name = jobcard.customer_name
        car.customer_phone = jobcard.customer_phone
        car.customer_address = jobcard.customer_address or ""
        car.customer_email = jobcard.customer_email or ""
        car.save(
            update_fields=[
                "all_job_cards",
                "customer_name",
                "customer_phone",
                "customer_address",
                "customer_email",
            ]
        )
        log_history(
            request,
            jobcard.pk,
            "job_cards",
            "created",
            _creation_changes(serialize_jobcard(jobcard)),
        )
        return Response(serialize_jobcard(jobcard), status=status.HTTP_201_CREATED)


class CompatJobCardDetailView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        jobcard = get_object_or_404(JobCard, pk=pk)
        if request.user.has_role(RoleName.MECHANIC) and not _is_assigned_mechanic(
            request.user, jobcard
        ):
            return Response(
                {"error": "You can only access vehicles assigned to you."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not _can_access_post_mechanic_jobcard(request.user, jobcard):
            return Response(
                {"error": "This vehicle is not available for your role yet."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(serialize_jobcard(jobcard))

    def patch(self, request, pk):
        jobcard = get_object_or_404(JobCard, pk=pk)
        if not _can_access_post_mechanic_jobcard(request.user, jobcard):
            return Response(
                {"error": "This vehicle is not available for your role yet."},
                status=status.HTTP_403_FORBIDDEN,
            )
        previous = serialize_jobcard(jobcard)
        locked_fields = {
            "parts",
            "labour",
            "subTotal",
            "discountAmt",
            "amount",
            "taxes",
            "insuranceDetails",
        }
        if jobcard.inventory_consumed_at and locked_fields.intersection(request.data):
            return Response(
                {
                    "error": "Cannot modify jobcard parts, labour, or totals after inventory has been consumed."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_insurance_details = None
        if "insuranceDetails" in request.data:
            _, normalized_insurance_details, insurance_error_response = (
                _validate_insurance_details_update(
                    request.user, jobcard, request.data.get("insuranceDetails")
                )
            )
            if insurance_error_response:
                return insurance_error_response

        if "parts" in request.data:
            try:
                save_jobcard_parts(jobcard, request.data.get("parts") or [])
            except JobCardPartError as exc:
                return Response({"error": exc.message}, status=exc.status_code)
        if "accessories" in request.data and not _can_edit_accessories(request.user):
            return Response(
                {"error": "Only service advisors can add or edit accessories."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if "assignedMechanicId" in request.data:
            _, assigned_mechanic_id, assigned_mechanic_error = (
                _validate_assigned_mechanic(request.data.get("assignedMechanicId"))
            )
            if assigned_mechanic_error:
                return Response(
                    {"error": assigned_mechanic_error},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        required_date = None
        if "requiredDate" in request.data:
            required_date_raw = request.data.get("requiredDate")
            if required_date_raw in (None, ""):
                return Response(
                    {"error": "requiredDate is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            required_date = _safe_date(required_date_raw)
            if not required_date:
                return Response(
                    {
                        "error": "requiredDate must be a valid date in YYYY-MM-DD format."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        field_map = {
            "parts": "parts",
            "labour": "labour",
            "accessories": "accessories",
            "labourChecklist": "labour_checklist",
            "suggestedParts": "suggested_parts",
            "recommendedLabour": "recommended_labour",
            "recommendedParts": "recommended_parts",
            "advisorNotes": "advisor_notes",
            "workflowStatus": "workflow_status",
            "approvedItems": "approved_items",
            "mechanicChecklist": "mechanic_checklist",
            "mechanicNotes": "mechanic_notes",
            "postDeliveryChecklist": "post_delivery_checklist",
            "postDeliveryImages": "post_delivery_images",
            "postDeliveryCompletedAt": "post_delivery_completed_at",
            "postDeliveryCompletedBy": "post_delivery_completed_by",
            "assignedMechanicId": "assigned_technician_id",
            "jobCardStatus": "job_card_status",
            "subTotal": "sub_total",
            "discountAmt": "discount_amount",
            "amount": "amount",
            "taxes": "taxes",
            "applyGst": "apply_gst",
            "insuranceDetails": "insurance_details",
            "companyName": "company_name",
            "companyPhoneNumber": "company_phone_number",
            "gstin": "gstin",
            "observationRemarks": "observation_remarks",
            "gatePassPDF": "gate_pass_pdf",
            "jobCardPDF": "job_card_pdf",
            "callingStatus": "calling_status",
        }
        updated_fields = []
        if required_date is not None:
            jobcard.required_date = required_date
            updated_fields.append("required_date")
        for source, target in field_map.items():
            if source in request.data:
                value = request.data[source]
                if (
                    source == "insuranceDetails"
                    and normalized_insurance_details is not None
                ):
                    value = normalized_insurance_details
                setattr(jobcard, target, value)
                updated_fields.append(target)

        target_job_card_status = int(jobcard.job_card_status or 0)
        target_workflow_status = jobcard.workflow_status

        if (
            "workflowStatus" not in request.data
            and target_job_card_status >= 5
            and target_workflow_status == JobCard.WorkflowStatus.MECHANIC_COMPLETED
        ):
            jobcard.workflow_status = (
                JobCard.WorkflowStatus.POST_DELIVERY_INSPECTION_PENDING
            )
            if "workflow_status" not in updated_fields:
                updated_fields.append("workflow_status")
            target_workflow_status = jobcard.workflow_status

        if (
            ("gatePassPDF" in request.data or target_job_card_status >= 6)
            and target_job_card_status < 7
            and target_workflow_status != JobCard.WorkflowStatus.POST_DELIVERY_COMPLETED
        ):
            return Response(
                {
                    "error": "Gate Pass cannot be generated before Post Delivery Inspection is completed."
                },
                status=status.HTTP_409_CONFLICT,
            )

        if "workflowStatus" not in request.data and target_job_card_status >= 7:
            jobcard.workflow_status = JobCard.WorkflowStatus.VEHICLE_COLLECTED
            if "workflow_status" not in updated_fields:
                updated_fields.append("workflow_status")

        if updated_fields:
            jobcard.save(update_fields=[*updated_fields, "updated_at"])
            log_history(
                request,
                jobcard.pk,
                "job_cards",
                "updated",
                _update_changes(previous, serialize_jobcard(jobcard)),
            )
        return Response(serialize_jobcard(jobcard))

    def delete(self, request, pk):
        jobcard = get_object_or_404(JobCard, pk=pk)
        previous = serialize_jobcard(jobcard)
        jobcard.delete()
        log_history(request, pk, "job_cards", "deleted", _deletion_changes(previous))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompatMechanicJobCardsView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _is_mechanic(request.user):
            return Response(
                {"error": "Only mechanic users can access the mechanic dashboard."},
                status=status.HTTP_403_FORBIDDEN,
            )

        workflow_statuses = [
            JobCard.WorkflowStatus.CUSTOMER_APPROVED,
            JobCard.WorkflowStatus.CUSTOMER_PARTIALLY_APPROVED,
            JobCard.WorkflowStatus.MECHANIC_IN_PROGRESS,
            JobCard.WorkflowStatus.MECHANIC_COMPLETED,
        ]
        qs = (
            JobCard.objects.select_related("temp_car__car")
            .prefetch_related("customer_approvals__items", "current_parts__product")
            .filter(
                workflow_status__in=workflow_statuses,
                assigned_technician_id=str(request.user.pk),
            )
            .order_by("-created_at")
        )
        return Response(
            _list_response([serialize_mechanic_jobcard(jobcard) for jobcard in qs])
        )


class CompatMechanicJobCardOpenView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not _is_mechanic(request.user):
            return Response(
                {"error": "Only mechanic users can open the checklist."},
                status=status.HTTP_403_FORBIDDEN,
            )

        jobcard = get_object_or_404(
            JobCard.objects.select_related("temp_car__car").prefetch_related(
                "customer_approvals__items", "current_parts__product"
            ),
            pk=pk,
        )

        if not _is_assigned_mechanic(request.user, jobcard):
            return Response(
                {"error": "You can only access vehicles assigned to you."},
                status=status.HTTP_403_FORBIDDEN,
            )

        allowed_statuses = {
            JobCard.WorkflowStatus.CUSTOMER_APPROVED,
            JobCard.WorkflowStatus.CUSTOMER_PARTIALLY_APPROVED,
            JobCard.WorkflowStatus.MECHANIC_IN_PROGRESS,
            JobCard.WorkflowStatus.MECHANIC_COMPLETED,
        }
        if jobcard.workflow_status not in allowed_statuses:
            return Response(
                {"error": "This vehicle is not available for mechanic processing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous = serialize_mechanic_jobcard(jobcard)
        previous_status = jobcard.workflow_status
        checklist, _ = _build_mechanic_checklist(jobcard)
        updated_fields = []

        if jobcard.mechanic_checklist != checklist:
            jobcard.mechanic_checklist = checklist
            updated_fields.append("mechanic_checklist")

        if jobcard.workflow_status in {
            JobCard.WorkflowStatus.CUSTOMER_APPROVED,
            JobCard.WorkflowStatus.CUSTOMER_PARTIALLY_APPROVED,
        }:
            jobcard.workflow_status = JobCard.WorkflowStatus.MECHANIC_IN_PROGRESS
            updated_fields.append("workflow_status")

        if updated_fields:
            jobcard.save(update_fields=[*updated_fields, "updated_at"])
            changes = []
            if previous_status != jobcard.workflow_status:
                changes.append(
                    {
                        "object": "workflowStatus",
                        "prevState": previous_status,
                        "currentState": jobcard.workflow_status,
                    }
                )
            changes.append(
                {
                    "object": "mechanicChecklist",
                    "prevState": previous.get("mechanicChecklist") or [],
                    "currentState": checklist,
                }
            )
            log_history(request, jobcard.pk, "job_cards", "updated", changes)

        return Response(serialize_mechanic_jobcard(jobcard), status=status.HTTP_200_OK)


class CompatMechanicJobCardProgressView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        if not _is_mechanic(request.user):
            return Response(
                {"error": "Only mechanic users can save checklist progress."},
                status=status.HTTP_403_FORBIDDEN,
            )

        jobcard = get_object_or_404(
            JobCard.objects.select_related("temp_car__car").prefetch_related(
                "customer_approvals__items", "current_parts__product"
            ),
            pk=pk,
        )

        if not _is_assigned_mechanic(request.user, jobcard):
            return Response(
                {"error": "You can only access vehicles assigned to you."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if jobcard.workflow_status == JobCard.WorkflowStatus.MECHANIC_COMPLETED:
            return Response(
                {"error": "Completed checklist is read-only."},
                status=status.HTTP_409_CONFLICT,
            )

        previous = serialize_mechanic_jobcard(jobcard)
        incoming_tasks = request.data.get("mechanicChecklist") or []
        checklist, _ = _build_mechanic_checklist(jobcard, incoming_tasks)

        updated_fields = []
        if jobcard.mechanic_checklist != checklist:
            jobcard.mechanic_checklist = checklist
            updated_fields.append("mechanic_checklist")
        if jobcard.mechanic_notes:
            jobcard.mechanic_notes = ""
            updated_fields.append("mechanic_notes")
        if jobcard.workflow_status != JobCard.WorkflowStatus.MECHANIC_IN_PROGRESS:
            jobcard.workflow_status = JobCard.WorkflowStatus.MECHANIC_IN_PROGRESS
            updated_fields.append("workflow_status")

        if updated_fields:
            jobcard.save(update_fields=[*updated_fields, "updated_at"])
            log_history(
                request,
                jobcard.pk,
                "job_cards",
                "updated",
                _update_changes(previous, serialize_mechanic_jobcard(jobcard)),
            )

        return Response(serialize_mechanic_jobcard(jobcard), status=status.HTTP_200_OK)


class CompatMechanicJobCardCompleteView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not _is_mechanic(request.user):
            return Response(
                {"error": "Only mechanic users can mark work completed."},
                status=status.HTTP_403_FORBIDDEN,
            )

        jobcard = get_object_or_404(
            JobCard.objects.select_related("temp_car__car").prefetch_related(
                "customer_approvals__items", "current_parts__product"
            ),
            pk=pk,
        )

        if not _is_assigned_mechanic(request.user, jobcard):
            return Response(
                {"error": "You can only access vehicles assigned to you."},
                status=status.HTTP_403_FORBIDDEN,
            )

        previous = serialize_mechanic_jobcard(jobcard)
        incoming_tasks = request.data.get("mechanicChecklist")

        checklist, approval_groups = _build_mechanic_checklist(jobcard, incoming_tasks)
        incomplete_tasks = [
            task["name"] for task in checklist if not task.get("completed")
        ]
        if approval_groups["approvedLabour"] and incomplete_tasks:
            return Response(
                {
                    "error": "All approved labour checklist items must be completed before marking work completed.",
                    "incompleteTasks": incomplete_tasks,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        jobcard.mechanic_checklist = checklist
        jobcard.mechanic_notes = ""
        jobcard.workflow_status = JobCard.WorkflowStatus.MECHANIC_COMPLETED
        jobcard.save(
            update_fields=[
                "mechanic_checklist",
                "mechanic_notes",
                "workflow_status",
                "updated_at",
            ]
        )

        log_history(
            request,
            jobcard.pk,
            "job_cards",
            "updated",
            _update_changes(previous, serialize_mechanic_jobcard(jobcard)),
        )
        return Response(serialize_mechanic_jobcard(jobcard), status=status.HTTP_200_OK)


class CompatPostDeliveryInspectionView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_jobcard(self, pk):
        return get_object_or_404(
            JobCard.objects.select_related("temp_car__car").prefetch_related(
                "customer_approvals__items", "current_parts__product", "invoices"
            ),
            pk=pk,
        )

    def get(self, request, pk):
        jobcard = self._get_jobcard(pk)
        if not _is_assigned_service_advisor(request.user, jobcard):
            return Response(
                {
                    "error": "Only the assigned service advisor can access Post Delivery Inspection."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not (
            _jobcard_ready_for_post_delivery(jobcard)
            or _jobcard_post_delivery_completed(jobcard)
        ):
            return Response(
                {
                    "error": "Post Delivery Inspection is available only after billing is completed."
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(serialize_post_delivery_jobcard(jobcard))

    def post(self, request, pk):
        jobcard = self._get_jobcard(pk)
        if not _is_assigned_service_advisor(request.user, jobcard):
            return Response(
                {
                    "error": "Only the assigned service advisor can complete Post Delivery Inspection."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if _jobcard_post_delivery_completed(jobcard):
            return Response(
                {"error": "Post Delivery Inspection has already been completed."},
                status=status.HTTP_409_CONFLICT,
            )

        if not _jobcard_ready_for_post_delivery(jobcard):
            return Response(
                {
                    "error": "Post Delivery Inspection is available only after billing is completed."
                },
                status=status.HTTP_409_CONFLICT,
            )

        previous = serialize_post_delivery_jobcard(jobcard)
        checklist, approved_labour = _build_post_delivery_checklist(
            jobcard, request.data.get("postDeliveryChecklist") or []
        )
        incomplete_tasks = [
            task["name"] for task in checklist if not task.get("completed")
        ]
        if approved_labour and incomplete_tasks:
            return Response(
                {
                    "error": "All approved labour items must be verified before submitting Post Delivery Inspection.",
                    "incompleteTasks": incomplete_tasks,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        images = _normalize_post_delivery_images(
            request.data.get("postDeliveryImages") or []
        )
        has_all_images, missing_image_types = _has_all_post_delivery_images(images)
        if not has_all_images:
            return Response(
                {
                    "error": "All final handover photos are required before submitting Post Delivery Inspection.",
                    "missingImageTypes": missing_image_types,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        jobcard.post_delivery_checklist = checklist
        jobcard.post_delivery_images = images
        jobcard.post_delivery_completed_at = timezone.now()
        jobcard.post_delivery_completed_by = getattr(request.user, "email", "") or str(
            request.user
        )
        jobcard.workflow_status = JobCard.WorkflowStatus.POST_DELIVERY_COMPLETED
        jobcard.save(
            update_fields=[
                "post_delivery_checklist",
                "post_delivery_images",
                "post_delivery_completed_at",
                "post_delivery_completed_by",
                "workflow_status",
                "updated_at",
            ]
        )

        log_history(
            request,
            jobcard.pk,
            "job_cards",
            "updated",
            _update_changes(previous, serialize_post_delivery_jobcard(jobcard)),
        )
        return Response(
            serialize_post_delivery_jobcard(jobcard), status=status.HTTP_200_OK
        )


class CompatJobCardSendApprovalView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        jobcard = get_object_or_404(JobCard, pk=pk)
        if not _is_assigned_service_advisor(request.user, jobcard):
            return Response(
                {
                    "error": "Only the assigned service advisor can send for customer approval."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if request.data.get("recommendedLabour") is not None:
            jobcard.recommended_labour = request.data.get("recommendedLabour") or []
        if request.data.get("recommendedParts") is not None:
            jobcard.recommended_parts = request.data.get("recommendedParts") or []
        if request.data.get("advisorNotes") is not None:
            jobcard.advisor_notes = request.data.get("advisorNotes") or ""
        jobcard.save(
            update_fields=[
                "recommended_labour",
                "recommended_parts",
                "advisor_notes",
                "updated_at",
            ]
        )

        try:
            approval = create_customer_approval(
                jobcard,
                created_by=getattr(request.user, "email", ""),
            )
        except CustomerApprovalError as exc:
            return Response({"error": exc.message}, status=exc.status_code)

        approval_payload = serialize_customer_approval(approval)
        log_history(
            request,
            jobcard.pk,
            "job_cards",
            "updated",
            [
                {
                    "object": "customerApproval",
                    "prevState": None,
                    "currentState": approval_payload,
                },
                {
                    "object": "workflowStatus",
                    "prevState": JobCard.WorkflowStatus.JOB_CARD_CREATED,
                    "currentState": JobCard.WorkflowStatus.WAITING_CUSTOMER_APPROVAL,
                },
            ],
        )
        return Response(approval_payload, status=status.HTTP_201_CREATED)


class CompatCustomerPortalSessionView(CompatAPIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        portal = _get_customer_portal_from_session(request)
        if not portal:
            return Response({"authenticated": False})
        return Response(_serialize_customer_portal_payload(portal))

    def post(self, request):
        submitted_plate = request.data.get("licensePlate") or ""
        car = _find_car_by_license_plate(submitted_plate)
        if not car:
            return Response(
                {"error": "Vehicle not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        portal = _ensure_customer_portal(car)
        _set_customer_portal_session(request, portal)
        return Response(_serialize_customer_portal_payload(portal))


class CompatCustomerPortalApprovalView(CompatAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, approval_id):
        portal = _get_customer_portal_from_session(request)
        if not portal:
            return Response(
                {"error": "Enter your vehicle license plate to continue."},
                status=status.HTTP_403_FORBIDDEN,
            )

        approval = get_object_or_404(
            CustomerApproval.objects.select_related(
                "job_card",
                "job_card__temp_car",
                "job_card__temp_car__car",
            ).prefetch_related("items", "job_card__invoices"),
            pk=approval_id,
        )

        approval_car = (
            approval.job_card.temp_car.car if approval.job_card.temp_car else None
        )
        if not approval_car or approval_car.pk != portal.car_id:
            return Response(
                {
                    "error": "This approval does not belong to the active portal session."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        item_decisions = request.data.get("itemDecisions") or {}
        customer_notes = request.data.get("customerNotes") or ""

        try:
            approval = submit_customer_approval(
                approval, item_decisions, customer_notes
            )
        except CustomerApprovalError as exc:
            return Response({"error": exc.message}, status=exc.status_code)

        approved_items = [
            serialize_approval_item(item)
            for item in approval.items.filter(approved=True)
        ]
        rejected_items = [
            serialize_approval_item(item)
            for item in approval.items.filter(approved=False)
        ]
        log_history(
            request,
            approval.job_card_id,
            "job_cards",
            "updated",
            [
                {
                    "object": "customerApprovalSubmitted",
                    "prevState": CustomerApproval.Status.PENDING,
                    "currentState": approval.status,
                },
                {
                    "object": "approvedItems",
                    "prevState": [],
                    "currentState": approved_items,
                },
                {
                    "object": "rejectedItems",
                    "prevState": [],
                    "currentState": rejected_items,
                },
                {
                    "object": "customerNotes",
                    "prevState": None,
                    "currentState": approval.customer_notes,
                },
                {
                    "object": "approvedAt",
                    "prevState": None,
                    "currentState": _iso(approval.approved_at),
                },
            ],
        )
        return Response(_serialize_customer_portal_payload(portal))


class CompatPartsView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        items = [
            serialize_product(product)
            for product in Product.objects.all().order_by("-created_at")
        ]
        return Response(_list_response(items))

    def post(self, request):
        product = Product.objects.create(
            name=request.data.get("partName", ""),
            sku=request.data.get("partNumber") or None,
            hsn=request.data.get("hsn") or None,
            category=request.data.get("category") or "",
            mrp=request.data.get("mrp") or 0,
            price=request.data.get("mrp") or 0,
            gst=request.data.get("gst") or 0,
            cgst=request.data.get("cgst") or 0,
            sgst=request.data.get("sgst") or 0,
            quantity=request.data.get("quantity") or 0,
            itemLocation=request.data.get("itemLocation") or "",
            vendorName=request.data.get("vendorName") or "",
            vendorCode=request.data.get("vendorCode") or "",
            purchasePrice=request.data.get("purchasePrice") or None,
            purchaseLocation=request.data.get("purchaseLocation") or "",
        )
        log_history(
            request,
            product.pk,
            "parts",
            "created",
            _creation_changes(serialize_product(product)),
        )
        return Response(serialize_product(product), status=status.HTTP_201_CREATED)


class CompatPartsDetailView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        previous = serialize_product(product)
        field_map = {
            "partName": "name",
            "partNumber": "sku",
            "hsn": "hsn",
            "category": "category",
            "mrp": "mrp",
            "gst": "gst",
            "cgst": "cgst",
            "sgst": "sgst",
            "quantity": "quantity",
            "itemCode": "itemCode",
            "itemLocation": "itemLocation",
            "vendorName": "vendorName",
            "vendorCode": "vendorCode",
            "purchasePrice": "purchasePrice",
            "purchaseLocation": "purchaseLocation",
        }
        updated_fields = []
        for source, target in field_map.items():
            if source in request.data:
                setattr(product, target, request.data[source])
                updated_fields.append(target)
                if source == "mrp" and "price" not in updated_fields:
                    product.price = request.data[source]
                    updated_fields.append("price")
        if updated_fields:
            product.save(update_fields=updated_fields)
            log_history(
                request,
                product.pk,
                "parts",
                "updated",
                _update_changes(previous, serialize_product(product)),
            )
        return Response(serialize_product(product))

    def delete(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        previous = serialize_product(product)
        product.delete()
        log_history(request, pk, "parts", "deleted", _deletion_changes(previous))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompatLabourView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        items = [
            serialize_labour(labour)
            for labour in Labour.objects.all().order_by("-created_at")
        ]
        return Response(_list_response(items))

    def post(self, request):
        labour = Labour.objects.create(
            labour_name=request.data.get("labourName", ""),
            labour_code=request.data.get("labourCode") or None,
            hsn=request.data.get("hsn") or "",
            category=request.data.get("category") or "",
            mrp=request.data.get("mrp") or 0,
            gst=request.data.get("gst") or 0,
            cgst=request.data.get("cgst") or 0,
            sgst=request.data.get("sgst") or 0,
        )
        log_history(
            request,
            labour.pk,
            "labour",
            "created",
            _creation_changes(serialize_labour(labour)),
        )
        return Response(serialize_labour(labour), status=status.HTTP_201_CREATED)


class CompatLabourDetailView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        labour = get_object_or_404(Labour, pk=pk)
        previous = serialize_labour(labour)
        labour.delete()
        log_history(request, pk, "labour", "deleted", _deletion_changes(previous))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompatInvoicesView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Invoice.objects.all().order_by("-created_at")
        created_gte = _safe_dt(request.query_params.get("created_gte"))
        created_lte = _safe_dt(request.query_params.get("created_lte"))
        invoice_type = request.query_params.get("invoiceType")
        invoice_series = request.query_params.get("invoiceSeries")
        if created_gte:
            qs = qs.filter(created_at__gte=created_gte)
        if created_lte:
            qs = qs.filter(created_at__lte=created_lte)
        if invoice_type:
            qs = qs.filter(invoice_type__iexact=invoice_type)
        if invoice_series:
            qs = qs.filter(invoice_series__iexact=invoice_series)
        return Response(_list_response([serialize_invoice(invoice) for invoice in qs]))

    def post(self, request):
        jobcard = get_object_or_404(JobCard, pk=request.data.get("jobCardId"))

        invoice_series = request.data.get("invoiceSeries", "")
        invoice_type = request.data.get("invoiceType", "")
        category = request.data.get("insuranceInvoiceType", "") or ""
        normalized_invoice_type = Invoice._normalized_label(invoice_type)

        requested_apply_gst = bool(request.data.get("applyGst", jobcard.apply_gst))
        if jobcard.apply_gst != requested_apply_gst:
            jobcard.apply_gst = requested_apply_gst
            jobcard.save(update_fields=["apply_gst", "updated_at"])

        effective_apply_gst = jobcard.apply_gst

        try:
            invoice_total, wallet_credit_used, final_amount = (
                _extract_invoice_financials(request.data)
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        if wallet_credit_used > 0 and str(category).strip().lower() == "insurance":
            return Response(
                {"error": "Wallet credits can only be used on the customer invoice."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if wallet_credit_used > 0 and not request.user.has_role(RoleName.BILLER):
            return Response(
                {"error": "Only billers can use wallet credits on invoices."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Reuse the same logical invoice across quote / pro-forma / tax invoice requests.
        existing = Invoice.find_existing_invoice(
            job_card=jobcard,
            invoice_series=invoice_series,
            invoice_type=invoice_type,
            category=category,
        )

        if existing:
            previous = serialize_invoice(existing)
            updated = False
            if invoice_type and invoice_type != existing.invoice_type:
                existing.invoice_type = invoice_type
                updated = True
            if category != existing.category:
                existing.category = category
                updated = True
            # update only fields that can change on regenerate
            if (
                "invoiceUrl" in request.data
                and request.data.get("invoiceUrl") != existing.invoice_url
            ):
                existing.invoice_url = request.data.get("invoiceUrl")
                updated = True
            if "isUpdatedInvoice" in request.data:
                val = request.data.get("isUpdatedInvoice", False)
                if existing.is_updated != val:
                    existing.is_updated = val
                    updated = True
            if (
                "invoiceCode" in request.data
                and request.data.get("invoiceCode") != existing.invoice_code
            ):
                existing.invoice_code = request.data.get("invoiceCode")
                updated = True
            if "isInsuranceInvoice" in request.data:
                val = request.data.get("isInsuranceInvoice", False)
                if existing.is_insurance_invoice != val:
                    existing.is_insurance_invoice = val
                    updated = True
            if (
                "carNumber" in request.data
                and request.data.get("carNumber") != existing.car_number
            ):
                existing.car_number = request.data.get("carNumber")
                updated = True
            if quantize_money(existing.invoice_total) != invoice_total:
                existing.invoice_total = invoice_total
                updated = True
            if (
                existing.wallet_transaction_id
                and quantize_money(existing.wallet_credit_used) != wallet_credit_used
            ):
                return Response(
                    {
                        "error": "Wallet credits have already been settled for this invoice and cannot be changed."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if quantize_money(existing.wallet_credit_used) != wallet_credit_used:
                existing.wallet_credit_used = wallet_credit_used
                updated = True
            if quantize_money(existing.final_amount) != final_amount:
                existing.final_amount = final_amount
                updated = True
            if existing.apply_gst != effective_apply_gst:
                existing.apply_gst = effective_apply_gst
                updated = True

            if updated:
                existing.save()
                log_history(
                    request,
                    existing.pk,
                    "invoice",
                    "updated",
                    _update_changes(previous, serialize_invoice(existing)),
                )

            if (
                normalized_invoice_type == "tax invoice"
                and wallet_credit_used > 0
                and not existing.wallet_transaction_id
            ):
                try:
                    apply_wallet_credit_to_invoice(
                        invoice=existing,
                        amount=wallet_credit_used,
                        invoice_total=invoice_total,
                        created_by=get_actor_display_name(request.user),
                    )
                except ValueError as exc:
                    return Response(
                        {"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST
                    )
                existing.refresh_from_db()

            if (
                invoice_consumes_inventory(invoice_type)
                and not jobcard.inventory_consumed_at
            ):
                try:
                    movements = consume_jobcard_inventory(jobcard, existing)
                except StockError as exc:
                    return Response({"error": exc.message}, status=exc.status_code)
                if movements:
                    existing.inventory_consumed_at = timezone.now()
                    existing.save(update_fields=["inventory_consumed_at"])

            return Response(serialize_invoice(existing), status=status.HTTP_200_OK)

        # Otherwise create; handle race where another process may create same invoice concurrently
        try:
            invoice = Invoice.objects.create(
                job_card=jobcard,
                invoice_series=invoice_series,
                invoice_type=invoice_type,
                category=category,
                invoice_number=request.data.get("invoiceNumber"),
                invoice_code=request.data.get("invoiceCode", ""),
                car_number=request.data.get("carNumber", ""),
                is_updated=request.data.get("isUpdatedInvoice", False),
                is_insurance_invoice=request.data.get("isInsuranceInvoice", False),
                invoice_total=invoice_total,
                wallet_credit_used=wallet_credit_used,
                final_amount=final_amount,
                apply_gst=effective_apply_gst,
                invoice_url=request.data.get("invoiceUrl", ""),
            )
        except IntegrityError:
            # Another process created it concurrently — return that one instead
            existing = Invoice.find_existing_invoice(
                job_card=jobcard,
                invoice_series=invoice_series,
                invoice_type=invoice_type,
                category=category,
            )
            if existing:
                return Response(serialize_invoice(existing), status=status.HTTP_200_OK)
            raise

        if normalized_invoice_type == "tax invoice" and wallet_credit_used > 0:
            try:
                apply_wallet_credit_to_invoice(
                    invoice=invoice,
                    amount=wallet_credit_used,
                    invoice_total=invoice_total,
                    created_by=get_actor_display_name(request.user),
                )
            except ValueError as exc:
                invoice.delete()
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            invoice.refresh_from_db()

        if invoice_consumes_inventory(invoice.invoice_type):
            try:
                movements = consume_jobcard_inventory(jobcard, invoice)
            except StockError as exc:
                invoice.delete()
                return Response({"error": exc.message}, status=exc.status_code)
            if movements:
                invoice.inventory_consumed_at = timezone.now()
                invoice.save(update_fields=["inventory_consumed_at"])

        log_history(
            request,
            invoice.pk,
            "invoice",
            "created",
            _creation_changes(serialize_invoice(invoice)),
        )
        return Response(serialize_invoice(invoice), status=status.HTTP_201_CREATED)


class CompatInvoicesByJobCardView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, jobcard_id):
        invoices = Invoice.objects.filter(job_card_id=jobcard_id).order_by(
            "-created_at"
        )
        return Response(
            _list_response([serialize_invoice(invoice) for invoice in invoices])
        )


class CompatInvoiceNextNumberView(CompatAPIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Get next invoice number",
        description="Atomically allocate or reuse the next invoice number for the given job card/spec.",
        tags=["Invoices"],
        responses={200: OpenApiResponse(description="Invoice number payload")},
    )
    def get(self, request, jobcard_id):
        invoice_series = request.query_params.get("invoice_series")
        invoice_type = request.query_params.get("invoice_type")
        category = request.query_params.get("category") or ""
        if not invoice_series or not invoice_type:
            return Response(
                {"error": "invoice_series and invoice_type are required query params"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        jobcard = get_object_or_404(JobCard, pk=jobcard_id)
        try:
            number = Invoice.get_or_create_number(
                job_card=jobcard,
                invoice_series=invoice_series,
                invoice_type=invoice_type,
                category=category,
            )
        except Exception as exc:
            return Response(
                {"error": f"Unable to determine invoice number: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "invoice_number": number,
                "invoice_code": f"{invoice_series}/{number}",
            },
            status=status.HTTP_200_OK,
        )


class CompatInvoiceDetailView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        previous = serialize_invoice(invoice)
        invoice.delete()
        log_history(request, pk, "invoice", "deleted", _deletion_changes(previous))
        return Response(status=status.HTTP_204_NO_CONTENT)


def _normalize_wallet_search_term(value):
    return "".join(str(value or "").upper().split())


def _wallet_pagination_values(request, *, default_page_size=10, max_page_size=100):
    try:
        page = int(request.query_params.get("page", 1))
    except (TypeError, ValueError):
        page = 1

    raw_page_size = request.query_params.get(
        "pageSize", request.query_params.get("page_size", default_page_size)
    )
    try:
        page_size = int(raw_page_size)
    except (TypeError, ValueError):
        page_size = default_page_size

    page = max(page, 1)
    page_size = max(1, min(page_size, max_page_size))
    return page, page_size


def serialize_wallet(wallet):
    total_credits_issued = getattr(wallet, "total_credits_issued", None)
    if total_credits_issued is None:
        total_credits_issued = wallet.transactions.filter(
            type=WalletTransaction.TransactionType.CREDIT
        ).aggregate(total=Sum("amount")).get("total") or Decimal("0.00")

    return {
        "$id": str(wallet.pk),
        "id": wallet.pk,
        "$createdAt": _iso(wallet.created_at),
        "$updatedAt": _iso(wallet.updated_at),
        "$permissions": [],
        "$databaseId": "django",
        "$collectionId": "wallets",
        "carId": wallet.car_id,
        "licensePlate": wallet.car.car_number,
        "customerName": wallet.car.customer_name,
        "vehicleModel": wallet.car.car_model,
        "balance": float(wallet.balance or 0),
        "totalCreditsIssued": float(total_credits_issued or 0),
    }


def serialize_wallet_transaction(transaction_row):
    return {
        "$id": str(transaction_row.pk),
        "id": transaction_row.pk,
        "walletId": transaction_row.wallet_id,
        "licensePlate": transaction_row.wallet.car.car_number,
        "amount": float(transaction_row.amount or 0),
        "reason": transaction_row.reason,
        "type": transaction_row.type,
        "createdBy": transaction_row.created_by,
        "createdAt": _iso(transaction_row.created_at),
    }


class CompatWalletsView(CompatAPIView):
    permission_classes = [IsBillerOnly]

    @extend_schema(
        summary="List customer wallets",
        description="List permanent-car wallets for the biller module with search and pagination.",
        tags=["Wallets"],
        responses={200: OpenApiResponse(description="Wallet list payload")},
    )
    def get(self, request):
        license_plate = request.query_params.get(
            "licensePlate"
        ) or request.query_params.get("license_plate")
        customer_name = request.query_params.get(
            "customerName"
        ) or request.query_params.get("customer_name")
        page, page_size = _wallet_pagination_values(request)

        wallets = CustomerWallet.objects.select_related("car").annotate(
            normalized_plate=Upper(
                Replace(
                    "car__car_number", Value(" "), Value(""), output_field=CharField()
                )
            ),
            total_credits_issued=Coalesce(
                Sum(
                    "transactions__amount",
                    filter=Q(
                        transactions__type=WalletTransaction.TransactionType.CREDIT
                    ),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Value(
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            ),
        )

        normalized_plate = _normalize_wallet_search_term(license_plate)
        if normalized_plate:
            wallets = wallets.filter(normalized_plate__icontains=normalized_plate)

        if customer_name:
            wallets = wallets.filter(
                car__customer_name__icontains=customer_name.strip()
            )

        wallets = wallets.order_by("car__car_number", "car_id")
        paginator = Paginator(wallets, page_size)
        page_obj = paginator.get_page(page)

        return Response(
            {
                "total": paginator.count,
                "page": page_obj.number,
                "pageSize": page_size,
                "totalPages": paginator.num_pages,
                "documents": [
                    serialize_wallet(wallet) for wallet in page_obj.object_list
                ],
            }
        )


class CompatWalletDetailView(CompatAPIView):
    permission_classes = [IsBillerOnly]

    @extend_schema(
        summary="Get wallet history",
        description="Return current balance and paginated wallet transactions for one permanent car.",
        tags=["Wallets"],
        responses={200: OpenApiResponse(description="Wallet detail payload")},
    )
    def get(self, request, car_id):
        car = get_object_or_404(Car, pk=car_id)
        wallet = ensure_wallet_for_car(car)
        page, page_size = _wallet_pagination_values(request)

        transaction_qs = wallet.transactions.select_related(
            "wallet", "wallet__car"
        ).order_by("-created_at", "-id")
        paginator = Paginator(transaction_qs, page_size)
        page_obj = paginator.get_page(page)

        return Response(
            {
                "wallet": serialize_wallet(wallet),
                "currentBalance": float(wallet.balance or 0),
                "transactions": {
                    "total": paginator.count,
                    "page": page_obj.number,
                    "pageSize": page_size,
                    "totalPages": paginator.num_pages,
                    "documents": [
                        serialize_wallet_transaction(transaction_row)
                        for transaction_row in page_obj.object_list
                    ],
                },
            }
        )


class CompatWalletAddCreditView(CompatAPIView):
    permission_classes = [IsBillerOnly]

    @extend_schema(
        summary="Add wallet credit",
        description="Create a CREDIT wallet transaction and increase the permanent-car wallet balance.",
        tags=["Wallets"],
        responses={201: OpenApiResponse(description="Wallet credit payload")},
    )
    def post(self, request, car_id):
        car = get_object_or_404(Car, pk=car_id)
        wallet = ensure_wallet_for_car(car)

        amount = request.data.get("amount")
        reason = str(request.data.get("reason") or "").strip()
        if amount in {None, ""}:
            return Response(
                {"error": "amount is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not reason:
            return Response(
                {"error": "reason is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            updated_wallet, transaction_row = add_wallet_credit(
                wallet=wallet,
                amount=amount,
                reason=reason,
                created_by=get_actor_display_name(request.user),
            )
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_history(
            request,
            transaction_row.pk,
            "wallet-transaction",
            "created",
            _creation_changes(serialize_wallet_transaction(transaction_row)),
        )

        return Response(
            {
                "wallet": serialize_wallet(updated_wallet),
                "transaction": serialize_wallet_transaction(transaction_row),
            },
            status=status.HTTP_201_CREATED,
        )


class CompatVehicleModelsView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        models = [
            serialize_vehicle_model(item)
            for item in VehilceModel.objects.all().order_by("make")
        ]
        return Response(_list_response(models))

    def post(self, request):
        item = VehilceModel.objects.create(
            make=request.data.get("make", ""),
            models=request.data.get("models", []),
        )
        log_history(
            request,
            item.pk,
            "car-model",
            "created",
            _creation_changes(serialize_vehicle_model(item)),
        )
        return Response(serialize_vehicle_model(item), status=status.HTTP_201_CREATED)

    def patch(self, request):
        model_id = request.data.get("id")
        item = get_object_or_404(VehilceModel, pk=model_id)
        previous = serialize_vehicle_model(item)
        if "make" in request.data:
            item.make = request.data["make"]
        if "models" in request.data:
            item.models = request.data["models"]
        item.save()
        log_history(
            request,
            item.pk,
            "car-model",
            "updated",
            _update_changes(previous, serialize_vehicle_model(item)),
        )
        return Response(serialize_vehicle_model(item))


class CompatInsuranceProvidersView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        providers = [
            serialize_insurance_provider(item)
            for item in InsuranceProvider.objects.all().order_by("insurer")
        ]
        return Response(_list_response(providers))

    def post(self, request):
        serializer = InsuranceProviderSerializer(
            data=_normalize_insurance_provider_payload(request.data)
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        provider = serializer.save()
        log_history(
            request,
            provider.pk,
            "insurance-providers",
            "created",
            _creation_changes(serialize_insurance_provider(provider)),
        )
        return Response(
            serialize_insurance_provider(provider), status=status.HTTP_201_CREATED
        )


class CompatInsuranceProviderDetailView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        provider = get_object_or_404(InsuranceProvider, id=pk)
        return Response(serialize_insurance_provider(provider))

    def patch(self, request, pk):
        provider = get_object_or_404(InsuranceProvider, id=pk)
        previous = serialize_insurance_provider(provider)
        serializer = InsuranceProviderSerializer(
            provider,
            data=_normalize_insurance_provider_payload(request.data),
            partial=True,
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        provider = serializer.save()
        log_history(
            request,
            provider.pk,
            "insurance-providers",
            "updated",
            _update_changes(previous, serialize_insurance_provider(provider)),
        )
        return Response(
            serialize_insurance_provider(provider), status=status.HTTP_200_OK
        )

    def delete(self, request, pk):
        provider = get_object_or_404(InsuranceProvider, id=pk)
        previous = serialize_insurance_provider(provider)
        provider.delete()
        log_history(
            request, pk, "insurance-providers", "deleted", _deletion_changes(previous)
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


CompatPolicyProvidersView = CompatInsuranceProvidersView
