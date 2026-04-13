from datetime import datetime
import json

from django.contrib.auth import authenticate, login, logout
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from auditlog.models import HistoryEntry
from billing.models import Invoice
from catalog.models.insurers_model import InsuranceProvider
from catalog.models.labour_models import Labour
from catalog.models.vehicle_models_model import VehilceModel
from inventory.models import Product
from jobcards.models import JobCard
from users.models import CustomUser
from vehicle_management.models import Car, TempCar

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

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


def _json_safe(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _filter_relevant_changes(data):
    excluded_fields = {
        "$collectionId",
        "$createdAt",
        "$updatedAt",
        "$id",
        "$permissions",
        "$databaseId",
    }
    return {key: _json_safe(value) for key, value in (data or {}).items() if key not in excluded_fields}


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
    user_payload = serialize_user(user) if getattr(user, "is_authenticated", False) else {}
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
    user_payload = serialize_user(request.user) if getattr(request.user, "is_authenticated", False) else {}
    HistoryEntry.objects.create(
        object_id=str(object_id),
        object_type=object_type,
        operation_type=operation_type,
        user_id=user_payload.get("$id", ""),
        user_email=user_payload.get("email", ""),
        user_name=user_payload.get("name", ""),
        history=_history_lines(str(object_id), object_type, operation_type, request.user, changes),
    )


def serialize_user(user):
    primary_role = user.get_primary_role()
    labels = []
    if primary_role:
        labels.append(primary_role)
    labels.extend(
        label.name for label in user.labels.exclude(name=primary_role) if label.name not in labels
    )
    full_name = f"{user.first_name} {user.last_name}".strip() or user.username
    return {
        "$id": str(user.pk),
        "name": full_name,
        "email": user.email,
        "labels": labels,
        "prefs": user.preferences or {},
        "status": bool(user.is_active),
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
    }
    return payload


def serialize_jobcard(jobcard):
    return {
        **_doc_meta(jobcard, "jobcards"),
        "serviceAdvisorID": jobcard.service_advisor_id,
        "carId": jobcard.car_id,
        "diagnosis": jobcard.diagnosis or [],
        "sendToPartsManager": jobcard.send_to_parts_manager,
        "carNumber": jobcard.car_number,
        "jobCardStatus": jobcard.job_card_status,
        "customerName": jobcard.customer_name,
        "customerPhone": jobcard.customer_phone,
        "customerAddress": jobcard.customer_address,
        "customerEmail": jobcard.customer_email,
        "parts": jobcard.parts or [],
        "labour": jobcard.labour or [],
        "images": jobcard.images or [],
        "observationRemarks": jobcard.observation_remarks or "",
        "subTotal": float(jobcard.sub_total),
        "totalDiscountAmt": float(jobcard.discount_amount),
        "amount": float(jobcard.amount),
        "jobCardNumber": jobcard.job_card_number,
        "insuranceDetails": jobcard.insurance_details or "",
        "purposeOfVisit": jobcard.purpose_of_visit or "",
        "taxes": jobcard.taxes or [],
        "gatePassPDF": jobcard.gate_pass_pdf or "",
        "jobCardPDF": jobcard.job_card_pdf or "",
        "carFuel": jobcard.car_fuel or "",
        "carOdometer": jobcard.bat_odometer or "",
        "gstin": jobcard.gstin,
        "callingStatus": jobcard.calling_status,
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
        "invoiceDate": _iso(invoice.created_at),
    }


def serialize_vehicle_model(item):
    return {
        **_doc_meta(item, "vehicle-models"),
        "make": item.make,
        "models": item.models or [],
    }


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return


@method_decorator(csrf_exempt, name="dispatch")
class CompatAPIView(APIView):
    authentication_classes = [CsrfExemptSessionAuthentication, BasicAuthentication]


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
                        "sessionDetails": {"$id": request.session.session_key or "current"},
                    }
                )
            return Response({"errorMsg": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

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
        return Response({"sessions": [{"$id": request.session.session_key or "current"}]})


class CompatUserListView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        users = [serialize_user(user) for user in CustomUser.objects.all().order_by("id")]
        return Response(users)

    def post(self, request):
        email = request.data.get("email", "").strip()
        password = request.data.get("password", "")
        name = request.data.get("name", "").strip()
        role = request.data.get("role")
        prefs = request.data.get("prefs", request.data.get("preferences"))

        if not email or not password:
            return Response(
                {"error": "email and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if prefs is not None and not isinstance(prefs, dict):
            return Response(
                {"error": "prefs must be an object"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if " " in name:
            first_name, last_name = name.split(" ", 1)
        else:
            first_name, last_name = name, ""

        user = CustomUser.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            preferences=prefs or {},
        )
        if role:
            user.set_single_role(role)
        return Response(serialize_user(user), status=status.HTTP_201_CREATED)


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
            "temp-cars": lambda qs: [serialize_temp_car(item) for item in qs.select_related("car")],
            "cars": lambda qs: [serialize_car(item) for item in qs],
            "parts": lambda qs: [serialize_product(item) for item in qs],
            "labour": lambda qs: [serialize_labour(item) for item in qs],
            "invoices": lambda qs: [serialize_invoice(item) for item in qs],
            "vehicle-models": lambda qs: [serialize_vehicle_model(item) for item in qs],
        }
        querysets = {
            "jobcards": JobCard.objects.filter(pk__in=ids),
            "temp-cars": TempCar.objects.filter(pk__in=ids),
            "cars": Car.objects.filter(pk__in=ids),
            "parts": Product.objects.filter(pk__in=ids),
            "labour": Labour.objects.filter(pk__in=ids),
            "invoices": Invoice.objects.filter(pk__in=ids),
            "vehicle-models": VehilceModel.objects.filter(pk__in=ids),
        }
        return Response(serializers[collection_name](querysets[collection_name]), status=status.HTTP_200_OK)


class CompatCarsView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cars = Car.objects.all().order_by("-id")
        updated_before = _safe_dt(request.query_params.get("updated_before"))
        if updated_before:
            cars = cars.filter(updated_at__lte=updated_before)
        return Response(_list_response([serialize_car(car) for car in cars]))

    def post(self, request):
        car = Car.objects.create(
            car_number=request.data.get("carNumber", ""),
            car_make=request.data.get("carMake", ""),
            car_model=request.data.get("carModel", ""),
            location=request.data.get("location", ""),
            purpose_of_visit_and_advisors=request.data.get("purposeOfVisitAndAdvisors", []),
        )
        car.cars_table_id = str(car.pk)
        car.save(update_fields=["cars_table_id"])
        log_history(request, car.pk, "cars", "created", _creation_changes(serialize_car(car)))
        return Response(serialize_car(car), status=status.HTTP_201_CREATED)


class CompatCarSearchView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        car_number = request.query_params.get("carNumber")
        term = request.query_params.get("q")
        qs = Car.objects.all().order_by("-id")
        if car_number:
            qs = qs.filter(car_number__iexact=car_number)
        elif term:
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
            car.save(update_fields=updated_fields)
            log_history(request, car.pk, "cars", "updated", _update_changes(previous, serialize_car(car)))
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
        temp_car = TempCar.objects.create(
            car=car,
            car_status=request.data.get("carStatus", 0),
            cars_table_id=request.data.get("carsTableId", str(car.pk)),
            purpose_of_visit_and_advisors=request.data.get("purposeOfVisitAndAdvisors", []),
            all_job_card_ids=request.data.get("allJobCardIds", []),
            job_card_id=request.data.get("jobCardId", ""),
        )
        log_history(request, temp_car.pk, "temp-cars", "created", _creation_changes(serialize_temp_car(temp_car)))
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
            log_history(request, temp_car.pk, "temp-cars", "updated", _update_changes(previous, serialize_temp_car(temp_car)))
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
        statuses = _parse_csvish_list(request.query_params.getlist("statuses"))
        if statuses:
            qs = qs.filter(job_card_status__in=statuses)
        created_gte = _safe_dt(request.query_params.get("created_gte"))
        created_lte = _safe_dt(request.query_params.get("created_lte"))
        if created_gte:
            qs = qs.filter(created_at__gte=created_gte)
        if created_lte:
            qs = qs.filter(created_at__lte=created_lte)
        return Response(_list_response([serialize_jobcard(jobcard) for jobcard in qs]))

    def post(self, request):
        temp_car = get_object_or_404(TempCar.objects.select_related("car"), pk=request.data.get("carId"))
        jobcard = JobCard.objects.create(
            car_id=str(temp_car.pk),
            temp_car=temp_car,
            diagnosis=request.data.get("diagnosis", []),
            send_to_parts_manager=request.data.get("sendToPartsManager", False),
            car_number=request.data.get("carNumber", temp_car.car.car_number),
            job_card_status=request.data.get("jobCardStatus", 0),
            customer_name=request.data.get("customerName", ""),
            customer_phone=request.data.get("customerPhone", ""),
            customer_address=request.data.get("customerAddress", ""),
            customer_email=request.data.get("customerEmail", ""),
            images=request.data.get("images", []),
            car_fuel=request.data.get("carFuel", ""),
            bat_odometer=request.data.get("carOdometer", ""),
            purpose_of_visit=request.data.get("purposeOfVisit", ""),
            job_card_pdf=request.data.get("jobCardPDF", ""),
            service_advisor_id=request.data.get("serviceAdvisorID", ""),
        )
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
        log_history(request, jobcard.pk, "job_cards", "created", _creation_changes(serialize_jobcard(jobcard)))
        return Response(serialize_jobcard(jobcard), status=status.HTTP_201_CREATED)


class CompatJobCardDetailView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        jobcard = get_object_or_404(JobCard, pk=pk)
        return Response(serialize_jobcard(jobcard))

    def patch(self, request, pk):
        jobcard = get_object_or_404(JobCard, pk=pk)
        previous = serialize_jobcard(jobcard)
        field_map = {
            "parts": "parts",
            "labour": "labour",
            "jobCardStatus": "job_card_status",
            "subTotal": "sub_total",
            "discountAmt": "discount_amount",
            "amount": "amount",
            "taxes": "taxes",
            "insuranceDetails": "insurance_details",
            "gstin": "gstin",
            "observationRemarks": "observation_remarks",
            "gatePassPDF": "gate_pass_pdf",
            "jobCardPDF": "job_card_pdf",
            "callingStatus": "calling_status",
        }
        updated_fields = []
        for source, target in field_map.items():
            if source in request.data:
                setattr(jobcard, target, request.data[source])
                updated_fields.append(target)
        if updated_fields:
            jobcard.save(update_fields=updated_fields)
            log_history(request, jobcard.pk, "job_cards", "updated", _update_changes(previous, serialize_jobcard(jobcard)))
        return Response(serialize_jobcard(jobcard))

    def delete(self, request, pk):
        jobcard = get_object_or_404(JobCard, pk=pk)
        previous = serialize_jobcard(jobcard)
        jobcard.delete()
        log_history(request, pk, "job_cards", "deleted", _deletion_changes(previous))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompatPartsView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        items = [serialize_product(product) for product in Product.objects.all().order_by("-created_at")]
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
        )
        log_history(request, product.pk, "parts", "created", _creation_changes(serialize_product(product)))
        return Response(serialize_product(product), status=status.HTTP_201_CREATED)


class CompatPartsDetailView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        previous = serialize_product(product)
        product.delete()
        log_history(request, pk, "parts", "deleted", _deletion_changes(previous))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompatLabourView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        items = [serialize_labour(labour) for labour in Labour.objects.all().order_by("-created_at")]
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
        log_history(request, labour.pk, "labour", "created", _creation_changes(serialize_labour(labour)))
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
            qs = qs.filter(invoice_type=invoice_type)
        if invoice_series:
            qs = qs.filter(invoice_series=invoice_series)
        return Response(_list_response([serialize_invoice(invoice) for invoice in qs]))

    def post(self, request):
        jobcard = get_object_or_404(JobCard, pk=request.data.get("jobCardId"))
        invoice = Invoice.objects.create(
            job_card=jobcard,
            invoice_series=request.data.get("invoiceSeries", ""),
            invoice_type=request.data.get("invoiceType", ""),
            category=request.data.get("insuranceInvoiceType", "") or "",
            invoice_number=request.data.get("invoiceNumber"),
            invoice_code=request.data.get("invoiceCode", ""),
            car_number=request.data.get("carNumber", ""),
            is_updated=request.data.get("isUpdatedInvoice", False),
            is_insurance_invoice=request.data.get("isInsuranceInvoice", False),
            invoice_url=request.data.get("invoiceUrl", ""),
        )
        log_history(request, invoice.pk, "invoice", "created", _creation_changes(serialize_invoice(invoice)))
        return Response(serialize_invoice(invoice), status=status.HTTP_201_CREATED)


class CompatInvoicesByJobCardView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, jobcard_id):
        invoices = Invoice.objects.filter(job_card_id=jobcard_id).order_by("-created_at")
        return Response(_list_response([serialize_invoice(invoice) for invoice in invoices]))


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


class CompatVehicleModelsView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        models = [serialize_vehicle_model(item) for item in VehilceModel.objects.all().order_by("make")]
        return Response(_list_response(models))

    def post(self, request):
        item = VehilceModel.objects.create(
            make=request.data.get("make", ""),
            models=request.data.get("models", []),
        )
        log_history(request, item.pk, "car-model", "created", _creation_changes(serialize_vehicle_model(item)))
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
        log_history(request, item.pk, "car-model", "updated", _update_changes(previous, serialize_vehicle_model(item)))
        return Response(serialize_vehicle_model(item))


class CompatPolicyProvidersView(CompatAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        providers = [
            {
                "insurer": item.insurer,
                "address": item.address,
                "GST": item.gst,
            }
            for item in InsuranceProvider.objects.all().order_by("insurer")
        ]
        return Response(providers)
