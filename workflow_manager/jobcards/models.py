import uuid
from django.db import models, transaction
from inventory.models import Product
from .models import TempCar
from django.db.models import F


class JobCardCounter(models.Model):
    """
    A single‐row table that tracks the last issued job_card_number.
    """

    name = models.CharField(max_length=50, unique=True, default="jobcard")
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.name}: {self.last_number}"


class JobCard(models.Model):
    """
    A work‐order linked to a TempCar.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    car_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="External/business-facing jobcard identifier",
    )

    temp_car = models.ForeignKey(
        TempCar,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_cards",
    )

    diagnosis = models.JSONField(default=list, blank=True)
    send_to_parts_manager = models.BooleanField(default=False)

    # vehicle & customer info
    car_number = models.CharField(max_length=100)
    job_card_status = models.IntegerField()
    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=15)
    customer_address = models.TextField(blank=True, null=True)
    customer_email = models.EmailField(blank=True, null=True)
    gstin = models.CharField(max_length=20, blank=True, null=True)

    # what’s done on the job
    parts = models.JSONField(default=list, blank=True)
    labour = models.JSONField(default=list, blank=True)
    images = models.JSONField(default=list, blank=True)

    # misc fields
    job_card_number = models.PositiveIntegerField()
    car_fuel = models.CharField(max_length=50, blank=True, null=True)
    bat_odometer = models.CharField(max_length=50, blank=True, null=True)
    insurance_details = models.TextField(blank=True, null=True)

    # financials
    sub_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taxes = models.JSONField(default=list, blank=True)

    # PDFs, passes, etc.
    job_card_pdf = models.URLField(blank=True, null=True)
    gate_pass_pdf = models.URLField(blank=True, null=True)

    purpose_of_visit = models.CharField(max_length=255, blank=True, null=True)
    service_advisor_id = models.CharField(max_length=100, blank=True, null=True)
    observation_remarks = models.TextField(blank=True, null=True)

    calling_status = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # only assign once
        if self.job_card_number is None:
            with transaction.atomic():
                # fetch (and create, if needed) the single counter row
                counter, _ = JobCardCounter.objects.select_for_update().get_or_create(
                    name="jobcard"
                )

                # bump by 1
                counter.last_number = F("last_number") + 1
                counter.save()

                # re‐load the actual integer value
                counter.refresh_from_db()
                self.job_card_number = counter.last_number

        super().save(*args, **kwargs)

    def __str__(self):
        return f"JobCard {self.car_id} (#{self.job_card_number})"


class CurrentPart(models.Model):
    """
    Snapshots the Product data at assignment time.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    job_card = models.ForeignKey(
        JobCard, on_delete=models.CASCADE, related_name="current_parts"
    )

    # link back to master Product
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, help_text="Master product record"
    )

    # snapshot of the product fields
    part_id = models.CharField(max_length=100)
    part_name = models.CharField(max_length=255)
    part_number = models.CharField(max_length=50)
    hsn = models.CharField(max_length=20, blank=True, null=True)

    quantity = models.PositiveIntegerField(default=1)

    # pricing & tax
    mrp = models.DecimalField(max_digits=30, decimal_places=2)
    discount_percentage = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )
    discounted_subtotal = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )
    discount_amount = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )

    insurance_percentage = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )
    insurance_subtotal = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )
    insurance_amount = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )

    sub_total = models.DecimalField(max_digits=30, decimal_places=2)
    total_tax = models.DecimalField(max_digits=30, decimal_places=2)
    amount = models.DecimalField(max_digits=30, decimal_places=2)

    gst = models.DecimalField(max_digits=5, decimal_places=2)
    cgst = models.DecimalField(max_digits=5, decimal_places=2)
    sgst = models.DecimalField(max_digits=5, decimal_places=2)
    cgst_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    sgst_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )

    customer_amount = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )
    customer_sub_total = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )
    customer_cgst_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    customer_sgst_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    customer_discount_amount = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )
    customer_total_tax = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )

    insurance_sub_total = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )
    insurance_cgst_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    insurance_sgst_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    insurance_total_tax = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )
    insurance_discount_amount = models.DecimalField(
        max_digits=30, decimal_places=2, blank=True, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.part_name} x{self.quantity} on JobCard {self.job_card.card_id}"


class CurrentLabour(models.Model):
    """
    A live‐work copy of a labour item on a TempCar.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # link back to the in-flight TempCar
    temp_car = models.ForeignKey(
        TempCar, on_delete=models.CASCADE, related_name="current_labours"
    )

    # snapshot of the master labour details
    labour_id = models.CharField(max_length=100)
    labour_name = models.CharField(max_length=255)
    labour_code = models.CharField(max_length=50)
    hsn_code = models.CharField(max_length=20, blank=True, null=True)

    # pricing & tax percentages
    mrp = models.DecimalField(max_digits=10, decimal_places=2)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    cgst = models.DecimalField(max_digits=5, decimal_places=2)
    sgst = models.DecimalField(max_digits=5, decimal_places=2)

    quantity = models.PositiveIntegerField(default=1)

    # calculated amounts
    sub_total = models.DecimalField(max_digits=12, decimal_places=2)
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2)
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

    # optional discount
    discount_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    discount_sub_total = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    # optional insurance cover
    insurance_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    insurance_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    insurance_sub_total = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    insurance_cgst_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    insurance_sgst_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    insurance_total_tax = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    insurance_discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    # optional customer‐payable breakdown
    customer_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    customer_sub_total = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    customer_cgst_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    customer_sgst_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    customer_total_tax = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    customer_discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.labour_name} on TempCar {self.temp_car.id}"
