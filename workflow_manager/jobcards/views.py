# yourapp/views.py
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import IntegrityError, DatabaseError

from .models import JobCard, Product, CurrentPart, CurrentLabour
from .serializers import (
    JobCardSerializer,
    CurrentPartSerializer,
    CurrentLabourSerializer,
)
from inventory.models import Product


class JobCardListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        GET /api/jobcards/
        """
        try:
            jobcards = JobCard.objects.all()
            serializer = JobCardSerializer(jobcards, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError:
            return Response(
                {"error": "Could not fetch job cards."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class JobCardCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        POST /api/jobcards/create/
        """
        serializer = JobCardSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            jobcard = serializer.save()
            return Response(
                JobCardSerializer(jobcard).data, status=status.HTTP_201_CREATED
            )
        except IntegrityError:
            return Response(
                {"error": "A job card with that identifier already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to create job card right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class JobCardDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """
        GET /api/jobcards/{pk}/
        """
        jobcard = get_object_or_404(JobCard, pk=pk)
        serializer = JobCardSerializer(jobcard)
        return Response(serializer.data, status=status.HTTP_200_OK)


class JobCardUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        """
        PUT /api/jobcards/{pk}/update/
        """
        jobcard = get_object_or_404(JobCard, pk=pk)
        serializer = JobCardSerializer(jobcard, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated = serializer.save()
            return Response(JobCardSerializer(updated).data, status=status.HTTP_200_OK)
        except IntegrityError:
            return Response(
                {"error": "Job card identifier conflicts with an existing record."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to update job card right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request, pk):
        """
        PATCH /api/jobcards/{pk}/update/
        """
        jobcard = get_object_or_404(JobCard, pk=pk)
        serializer = JobCardSerializer(jobcard, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated = serializer.save()
            return Response(JobCardSerializer(updated).data, status=status.HTTP_200_OK)
        except IntegrityError:
            return Response(
                {"error": "Job card identifier conflicts with an existing record."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to patch job card right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class JobCardDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        """
        DELETE /api/jobcards/{pk}/delete/
        """
        jobcard = get_object_or_404(JobCard, pk=pk)
        try:
            jobcard.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError:
            return Response(
                {"error": "Unable to delete job card right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CurrentPartListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            items = CurrentPart.objects.all()
            serializer = CurrentPartSerializer(items, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError:
            return Response(
                {"error": "Could not fetch current parts."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CurrentPartCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CurrentPartSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            item = serializer.save()
            return Response(
                CurrentPartSerializer(item).data, status=status.HTTP_201_CREATED
            )
        except IntegrityError:
            return Response(
                {"error": "Integrity error creating current part."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to create current part right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CurrentPartDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        item = get_object_or_404(CurrentPart, pk=pk)
        serializer = CurrentPartSerializer(item)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CurrentPartUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        item = get_object_or_404(CurrentPart, pk=pk)
        serializer = CurrentPartSerializer(item, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            updated = serializer.save()
            return Response(
                CurrentPartSerializer(updated).data, status=status.HTTP_200_OK
            )
        except IntegrityError:
            return Response(
                {"error": "Integrity error updating current part."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to update current part right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request, pk):
        item = get_object_or_404(CurrentPart, pk=pk)
        serializer = CurrentPartSerializer(item, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            updated = serializer.save()
            return Response(
                CurrentPartSerializer(updated).data, status=status.HTTP_200_OK
            )
        except IntegrityError:
            return Response(
                {"error": "Integrity error patching current part."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to patch current part right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CurrentPartDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        item = get_object_or_404(CurrentPart, pk=pk)
        try:
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError:
            return Response(
                {"error": "Unable to delete current part right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CurrentLabourListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            items = CurrentLabour.objects.all()
            serializer = CurrentLabourSerializer(items, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except DatabaseError:
            return Response(
                {"error": "Could not fetch current labours."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CurrentLabourCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CurrentLabourSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            item = serializer.save()
            return Response(
                CurrentLabourSerializer(item).data, status=status.HTTP_201_CREATED
            )
        except IntegrityError:
            return Response(
                {"error": "Integrity error creating current labour."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to create current labour right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CurrentLabourDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        item = get_object_or_404(CurrentLabour, pk=pk)
        serializer = CurrentLabourSerializer(item)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CurrentLabourUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        item = get_object_or_404(CurrentLabour, pk=pk)
        serializer = CurrentLabourSerializer(item, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            updated = serializer.save()
            return Response(
                CurrentLabourSerializer(updated).data, status=status.HTTP_200_OK
            )
        except IntegrityError:
            return Response(
                {"error": "Integrity error updating current labour."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to update current labour right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request, pk):
        item = get_object_or_404(CurrentLabour, pk=pk)
        serializer = CurrentLabourSerializer(item, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            updated = serializer.save()
            return Response(
                CurrentLabourSerializer(updated).data, status=status.HTTP_200_OK
            )
        except IntegrityError:
            return Response(
                {"error": "Integrity error patching current labour."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {"error": "Unable to patch current labour right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CurrentLabourDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        item = get_object_or_404(CurrentLabour, pk=pk)
        try:
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DatabaseError:
            return Response(
                {"error": "Unable to delete current labour right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AddPartsToJobCardView(APIView):
    """
    Add/update/delete multiple CurrentPart entries on a JobCard.
    """

    def post(self, request, jobcard_id):
        # 1) fetch the jobcard
        jobcard = get_object_or_404(JobCard, id=jobcard_id)

        # 2) incoming parts payload
        parts = request.data.get("parts", [])

        # 3) delete any parts removed on the client
        existing = CurrentPart.objects.filter(job_card=jobcard)
        received = {p["product_id"] for p in parts}
        to_delete = existing.exclude(product_id__in=received)
        to_delete.delete()

        added_or_updated = []
        http_code = status.HTTP_200_OK

        for p in parts:
            pid = p.get("product_id")
            qty = int(p.get("quantity", 1))

            # validate master product exists
            try:
                product = Product.objects.get(id=pid)
            except Product.DoesNotExist:
                return Response(
                    {"error": f"Product {pid} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # create or update snapshot
            cp, created = CurrentPart.objects.get_or_create(
                job_card=jobcard, product=product, defaults={}
            )

            # pull in all snapshot fields
            cp.part_id = str(product.id)
            cp.part_name = product.name
            cp.part_number = product.sku or ""
            cp.hsn = product.hsn or ""
            cp.quantity = qty

            # if you’re providing the tax/price breakdown in the payload, trust it:
            for fld in (
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
            ):
                if fld in p:
                    setattr(cp, fld, p[fld])

            try:
                cp.save()
            except DatabaseError:
                return Response(
                    {"error": "Database error saving part."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            added_or_updated.append(CurrentPartSerializer(cp).data)
            http_code = (
                status.HTTP_201_CREATED if created else status.HTTP_204_NO_CONTENT
            )

        return Response({"added_or_updated_parts": added_or_updated}, status=http_code)


class AddLaboursToJobCardView(APIView):
    """
    Add/update/delete multiple CurrentLabour entries on a JobCard’s TempCar.
    """

    def post(self, request, jobcard_id):
        jobcard = get_object_or_404(JobCard, id=jobcard_id)

        # ensure we have a temp_car to attach to
        if not jobcard.temp_car:
            return Response(
                {"error": "JobCard has no TempCar"}, status=status.HTTP_400_BAD_REQUEST
            )

        labours = request.data.get("labours", [])

        existing = CurrentLabour.objects.filter(temp_car=jobcard.temp_car)
        received = {l["labour_id"] for l in labours}
        to_delete = existing.exclude(labour_id__in=received)
        to_delete.delete()

        added_or_updated = []
        http_code = status.HTTP_200_OK

        for l in labours:
            lid = l.get("labour_id")
            qty = int(l.get("quantity", 1))

            # create or update snapshot
            cl, created = CurrentLabour.objects.get_or_create(
                temp_car=jobcard.temp_car, labour_id=lid, defaults={}
            )

            # pull in all fields from payload
            cl.labour_name = l.get("labour_name", cl.labour_name)
            cl.labour_code = l.get("labour_code", cl.labour_code)
            cl.hsn_code = l.get("hsn_code", cl.hsn_code)
            cl.mrp = l.get("mrp", cl.mrp)
            cl.gst_percentage = l.get("gst_percentage", cl.gst_percentage)
            cl.cgst = l.get("cgst", cl.cgst)
            cl.sgst = l.get("sgst", cl.sgst)
            cl.quantity = qty

            for fld in (
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
            ):
                if fld in l:
                    setattr(cl, fld, l[fld])

            try:
                cl.save()
            except DatabaseError:
                return Response(
                    {"error": "Database error saving labour."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            added_or_updated.append(CurrentLabourSerializer(cl).data)
            http_code = (
                status.HTTP_201_CREATED if created else status.HTTP_204_NO_CONTENT
            )

        return Response(
            {"added_or_updated_labours": added_or_updated}, status=http_code
        )


class FinalizeJobCardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, jobcard_id):
        """
        POST /api/jobcards/{jobcard_id}/finalize/
        """
        jobcard = get_object_or_404(JobCard, id=jobcard_id)

        # Deduct quantities from inventory for each CurrentPart
        for cp in jobcard.current_parts.all():
            product = cp.product
            if product.quantity >= cp.quantity:
                product.quantity -= cp.quantity
                try:
                    product.save()
                except DatabaseError:
                    return Response(
                        {"error": f"Failed to update stock for {product.name}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
            else:
                return Response(
                    {"error": f"Not enough stock for {product.name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Mark the JobCard as finalized (e.g. status code 4 = Completed)
        jobcard.job_card_status = 4
        jobcard.save()

        return Response(
            {"message": "JobCard finalized and inventory updated."},
            status=status.HTTP_200_OK,
        )
