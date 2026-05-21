from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction, IntegrityError, DatabaseError
from django.utils import timezone
from rest_framework.exceptions import NotFound
from jobcards.models import JobCard
from inventory.services import (
    StockError,
    consume_jobcard_inventory,
    invoice_consumes_inventory,
)
from users.permissions import IsBillerOrAdmin
from .models import Invoice
from .serializers import InvoiceSerializer
from drf_spectacular.utils import extend_schema, extend_schema_view


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
                    invoice_url=data["invoice_url"],
                )
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
