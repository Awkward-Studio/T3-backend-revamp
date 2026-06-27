from decimal import Decimal

from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import CharField, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, Replace, Upper
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from inventory.services import (
    StockError,
    consume_jobcard_inventory,
    invoice_consumes_inventory,
)
from jobcards.models import JobCard
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from users.models import RoleName
from users.permissions import IsBillerOnly, IsBillerOrAdmin
from vehicle_management.models import Car

from .models import CustomerWallet, Invoice, WalletTransaction
from .serializers import (
    AddWalletCreditSerializer,
    CustomerWalletSerializer,
    InvoiceSerializer,
    InvoiceWalletCreditSerializer,
    WalletTransactionSerializer,
)
from .services import (
    add_wallet_credit,
    apply_wallet_credit_to_invoice,
    ensure_wallet_for_car,
    get_actor_display_name,
    quantize_money,
)


def normalize_invoice_type(invoice_type):
    value = str(invoice_type or "").strip().lower()
    value = value.replace("-", " ").replace("_", " ")
    if value == "quote":
        return "quote"
    if value in {"proforma", "pro forma", "pro forma invoice", "proforma invoice"}:
        return "pro forma invoice"
    if value in {"tax", "tax invoice"}:
        return "tax invoice"
    return str(invoice_type or "").strip()


def normalize_series(series):
    return str(series or "").strip().lower()


def normalize_category(category, invoice_type):
    if normalize_invoice_type(invoice_type) == "quote":
        return ""
    return str(category or "").strip().lower()


def get_invoice_financials(data):
    serializer = InvoiceWalletCreditSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    invoice_total = quantize_money(serializer.validated_data.get("invoice_total"))
    wallet_credit_used = quantize_money(
        serializer.validated_data.get("wallet_credit_used")
    )
    final_amount = quantize_money(serializer.validated_data.get("final_amount"))

    if wallet_credit_used < 0:
        raise ValueError("Credit amount cannot be negative.")
    if invoice_total < 0:
        raise ValueError("Invoice total cannot be negative.")
    if final_amount < 0:
        raise ValueError("Final amount cannot be negative.")
    if wallet_credit_used > invoice_total:
        raise ValueError("Credit amount cannot exceed invoice total.")

    expected_final_amount = quantize_money(invoice_total - wallet_credit_used)
    if final_amount in {Decimal("0.00"), expected_final_amount}:
        final_amount = expected_final_amount
    else:
        raise ValueError("Final amount must equal invoice total minus credits used.")

    return invoice_total, wallet_credit_used, final_amount


def user_can_apply_wallet_credits(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False) and user.has_role(RoleName.BILLER)
    )


# @TODO: use serializers
class GetNextInvoiceNumberView(APIView):
    permission_classes = [IsBillerOrAdmin]

    @extend_schema(
        summary="Get next invoice number",
        description="Retrieve the next invoice number for a given job card and invoice series/type.",
        tags=["Invoices"],
    )
    def get(self, request, jobcard_id):

        jobcard = get_object_or_404(JobCard, id=jobcard_id)
        invoice_series = normalize_series(request.query_params.get("invoice_series"))
        inv_type = normalize_invoice_type(request.query_params.get("invoice_type"))
        category = normalize_category(request.query_params.get("category"), inv_type)

        if not invoice_series or not inv_type:
            return Response(
                {"error": "invoice_series and invoice_type are required query params"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            number = Invoice.get_or_create_number(
                jobcard, invoice_series, inv_type, category
            )
            return Response({"invoice_number": number}, status=status.HTTP_200_OK)

        except Invoice.DoesNotExist:
            return Response(
                {"error": "Unable to determine invoice number."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except DatabaseError as db_err:
            return Response(
                {"error": "Database error: " + str(db_err)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as exc:
            return Response(
                {"error": "Unexpected error: " + str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreateInvoiceView(APIView):
    permission_classes = [IsBillerOrAdmin]

    @extend_schema(
        summary="Create a new invoice",
        description="Create a new invoice record for a job card.",
        tags=["Invoices"],
    )
    def post(self, request):
        """
        POST /api/invoices/create/
        {
          "job_card": "...uuid...",
          "invoice_series": "bds",
          "invoice_type": "proforma",
          "category": "insurance",   # omit for quote
          "invoice_code": "INV-BDS-PF-0003",
          "is_updated": false,
          "invoice_url": "https://..."
        }
        """
        data = request.data
        required = (
            "job_card",
            "invoice_series",
            "invoice_type",
            "invoice_url",
            "invoice_number",
        )
        missing = [f for f in required if f not in data]
        if missing:
            return Response(
                {"error": f"Missing required fields: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        jobcard = get_object_or_404(JobCard, id=data["job_card"])
        invoice_series = normalize_series(data["invoice_series"])
        inv_type = normalize_invoice_type(data["invoice_type"])
        category = normalize_category(data.get("category"), inv_type)
        number = data["invoice_number"]
        if not number:
            return Response(
                {"error": "invoice_number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requested_apply_gst = bool(data.get("apply_gst", jobcard.apply_gst))
        if jobcard.apply_gst != requested_apply_gst:
            jobcard.apply_gst = requested_apply_gst
            jobcard.save(update_fields=["apply_gst", "updated_at"])

        effective_apply_gst = jobcard.apply_gst

        try:
            invoice_total, wallet_credit_used, final_amount = get_invoice_financials(
                data
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        if wallet_credit_used > 0 and category == "insurance":
            return Response(
                {"error": "Wallet credits can only be used on the customer invoice."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if wallet_credit_used > 0 and not user_can_apply_wallet_credits(request.user):
            return Response(
                {"error": "Only billers can use wallet credits on invoices."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            with transaction.atomic():
                inv = Invoice.objects.create(
                    job_card=jobcard,
                    invoice_series=invoice_series,
                    invoice_type=inv_type,
                    category=category or "",
                    invoice_number=number,
                    invoice_code=data.get("invoice_code", ""),
                    is_updated=data.get("is_updated", False),
                    is_insurance_invoice=data.get("is_insurance_invoice", False),
                    car_number=data.get("car_number", jobcard.car_number),
                    invoice_total=invoice_total,
                    wallet_credit_used=wallet_credit_used,
                    final_amount=final_amount,
                    apply_gst=effective_apply_gst,
                    invoice_url=data["invoice_url"],
                )
                if wallet_credit_used > 0:
                    apply_wallet_credit_to_invoice(
                        invoice=inv,
                        amount=wallet_credit_used,
                        invoice_total=invoice_total,
                        created_by=get_actor_display_name(request.user),
                    )
                    inv.refresh_from_db()

                if invoice_consumes_inventory(inv_type):
                    movements = consume_jobcard_inventory(jobcard, invoice=inv)
                    if movements:
                        inv.inventory_consumed_at = timezone.now()
                        inv.save(update_fields=["inventory_consumed_at", "updated_at"])
        except IntegrityError as ie:
            return Response(
                {"error": "Integrity error saving invoice: " + str(ie)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except StockError as exc:
            return Response({"error": exc.message}, status=exc.status_code)
        except DatabaseError as db_err:
            return Response(
                {"error": "Database error saving invoice: " + str(db_err)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as exc:
            return Response(
                {"error": "Unexpected error: " + str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(InvoiceSerializer(inv).data, status=status.HTTP_201_CREATED)


class InvoiceListView(APIView):
    permission_classes = [IsBillerOrAdmin]

    @extend_schema(
        summary="List invoices for a job card",
        description="Retrieve a list of invoices for a specific job card.",
        tags=["Invoices"],
    )
    def get(self, request, jobcard_id):
        """
        GET /api/jobcards/{jobcard_id}/invoices/
        """
        jobcard = get_object_or_404(JobCard, id=jobcard_id)
        try:
            qs = Invoice.objects.filter(job_card=jobcard).order_by(
                "invoice_series", "invoice_type", "invoice_number"
            )
            return Response(
                InvoiceSerializer(qs, many=True).data, status=status.HTTP_200_OK
            )
        except DatabaseError as db_err:
            return Response(
                {"error": "Database error fetching invoices: " + str(db_err)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as exc:
            return Response(
                {"error": "Unexpected error: " + str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InvoiceDetailView(APIView):
    permission_classes = [IsBillerOrAdmin]

    @extend_schema(
        summary="Retrieve an invoice",
        description="Get detailed information about a specific invoice.",
        tags=["Invoices"],
    )
    def get(self, request, invoice_id):
        try:
            inv = get_object_or_404(Invoice, id=invoice_id)
        except NotFound:
            return Response(
                {"error": "Invoice not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as exc:
            return Response(
                {"error": f"Unexpected error: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(InvoiceSerializer(inv).data)

    @extend_schema(
        summary="Update an invoice",
        description="Update all fields of an invoice record that are allowed to be modified.",
        tags=["Invoices"],
    )
    def put(self, request, invoice_id):
        """
        PUT  /api/invoices/{invoice_id}/update/
        Full update of updatable fields.
        """
        inv = get_object_or_404(Invoice, id=invoice_id)
        try:
            for fld in (
                "invoice_url",
                "invoice_code",
                "invoice_series",
                "invoice_type",
                "is_updated",
            ):
                if fld in request.data:
                    setattr(inv, fld, request.data[fld])
            if "apply_gst" in request.data:
                apply_gst = bool(request.data.get("apply_gst", True))
                inv.apply_gst = apply_gst
                if inv.job_card.apply_gst != apply_gst:
                    inv.job_card.apply_gst = apply_gst
                    inv.job_card.save(update_fields=["apply_gst", "updated_at"])
            inv.save()
            return Response(InvoiceSerializer(inv).data, status=status.HTTP_200_OK)
        except IntegrityError as ie:
            return Response(
                {"error": f"Integrity error updating invoice: {ie}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError as db_err:
            return Response(
                {"error": f"Database error updating invoice: {db_err}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Partially update an invoice",
        description="Update specific fields of an invoice record that are allowed to be modified.",
        tags=["Invoices"],
    )
    def patch(self, request, invoice_id):
        """
        PATCH /api/invoices/{invoice_id}/partial-update/
        Partial update of updatable fields.
        """
        inv = get_object_or_404(Invoice, id=invoice_id)
        try:
            for fld in (
                "invoice_url",
                "invoice_code",
                "invoice_series",
                "invoice_type",
                "is_updated",
            ):
                if fld in request.data:
                    setattr(inv, fld, request.data[fld])
            if "apply_gst" in request.data:
                apply_gst = bool(request.data.get("apply_gst", True))
                inv.apply_gst = apply_gst
                if inv.job_card.apply_gst != apply_gst:
                    inv.job_card.apply_gst = apply_gst
                    inv.job_card.save(update_fields=["apply_gst", "updated_at"])
            inv.save()
            return Response(InvoiceSerializer(inv).data, status=status.HTTP_200_OK)
        except IntegrityError as ie:
            return Response(
                {"error": f"Integrity error patching invoice: {ie}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError as db_err:
            return Response(
                {"error": f"Database error patching invoice: {db_err}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Delete an invoice",
        description="Delete an invoice record.",
        tags=["Invoices"],
    )
    def delete(self, request, invoice_id):
        """
        DELETE /api/invoices/{invoice_id}/delete/
        """
        inv = get_object_or_404(Invoice, id=invoice_id)
        try:
            inv.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError as db_err:
            return Response(
                {"error": f"Database error deleting invoice: {db_err}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


def normalize_wallet_search_term(value):
    return "".join(str(value or "").upper().split())


def get_pagination_values(request, *, default_page_size=10, max_page_size=100):
    try:
        page = int(request.query_params.get("page", 1))
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = int(request.query_params.get("page_size", default_page_size))
    except (TypeError, ValueError):
        page_size = default_page_size

    page = max(page, 1)
    page_size = max(1, min(page_size, max_page_size))
    return page, page_size


class CustomerWalletListView(APIView):
    permission_classes = [IsBillerOnly]

    @extend_schema(
        summary="List customer wallets",
        description="List permanent-car wallets with optional search and pagination.",
        tags=["Wallets"],
    )
    def get(self, request):
        license_plate = request.query_params.get("license_plate")
        customer_name = request.query_params.get("customer_name")
        page, page_size = get_pagination_values(request)

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

        normalized_plate = normalize_wallet_search_term(license_plate)
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
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "results": CustomerWalletSerializer(
                    page_obj.object_list, many=True
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class CustomerWalletDetailView(APIView):
    permission_classes = [IsBillerOnly]

    @extend_schema(
        summary="Retrieve customer wallet history",
        description="Get a permanent car wallet summary and paginated transaction history.",
        tags=["Wallets"],
    )
    def get(self, request, car_id):
        car = get_object_or_404(Car, pk=car_id)
        wallet = ensure_wallet_for_car(car)
        page, page_size = get_pagination_values(request)

        transaction_qs = wallet.transactions.order_by("-created_at", "-id")
        paginator = Paginator(transaction_qs, page_size)
        page_obj = paginator.get_page(page)

        wallet_data = CustomerWalletSerializer(wallet).data
        return Response(
            {
                "wallet": wallet_data,
                "current_balance": wallet_data["balance"],
                "transactions": {
                    "count": paginator.count,
                    "page": page_obj.number,
                    "page_size": page_size,
                    "num_pages": paginator.num_pages,
                    "results": WalletTransactionSerializer(
                        page_obj.object_list, many=True
                    ).data,
                },
            },
            status=status.HTTP_200_OK,
        )


class CustomerWalletAddCreditView(APIView):
    permission_classes = [IsBillerOnly]

    @extend_schema(
        summary="Add customer wallet credit",
        description="Add a credit note or other wallet credit to a permanent car wallet.",
        tags=["Wallets"],
        request=AddWalletCreditSerializer,
    )
    def post(self, request, car_id):
        car = get_object_or_404(Car, pk=car_id)
        wallet = ensure_wallet_for_car(car)

        serializer = AddWalletCreditSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated_wallet, transaction_row = add_wallet_credit(
                wallet=wallet,
                amount=serializer.validated_data["amount"],
                reason=serializer.validated_data["reason"],
                created_by=get_actor_display_name(request.user),
            )
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "wallet": CustomerWalletSerializer(updated_wallet).data,
                "transaction": WalletTransactionSerializer(transaction_row).data,
            },
            status=status.HTTP_201_CREATED,
        )
