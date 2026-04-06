import uuid
from django.db import models, transaction
from django.db.models import F
from jobcards.models import JobCard


class InvoiceCounter(models.Model):
    SERIES_CHOICES = [
        ("bds", "BDS"),
        ("src", "SRC"),
    ]

    series = models.CharField(max_length=10, choices=SERIES_CHOICES, unique=True)
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.series} → {self.last_number}"


class Invoice(models.Model):
    SERIES_CHOICES = InvoiceCounter.SERIES_CHOICES
    TYPE_CHOICES = InvoiceCounter.TYPE_CHOICES
    CATEGORY_CHOICES = [
        ("customer", "Customer"),
        ("insurance", "Insurance"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_card = models.ForeignKey(
        JobCard, on_delete=models.CASCADE, related_name="invoices"
    )
    job_card_id = models.CharField(max_length=50, blank=True)
    invoice_series = models.CharField(max_length=10, choices=SERIES_CHOICES)
    invoice_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    invoice_number = models.PositiveIntegerField()
    invoice_code = models.CharField(max_length=50, blank=True)  # your custom code
    car_number = models.CharField(max_length=50, blank=True)  # your custom code
    is_updated = models.BooleanField(default=False)  # parallels your isUpdatedInvoice
    is_insurance_invoice = models.BooleanField(default=False)
    invoice_url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("invoice_series", "invoice_type", "invoice_number")
        ordering = ["invoice_series", "invoice_type", "invoice_number"]

    def __str__(self):
        return (
            f"{self.get_invoice_series_display()} {self.get_invoice_type_display()} "
            f"[{self.category}] #{self.invoice_number}"
        )

    @classmethod
    def _next_number(cls, invoice_series: str) -> int:
        """
        Atomically bump and return the next number for (invoice_series, invoice_type).
        """
        with transaction.atomic():
            counter, _ = InvoiceCounter.objects.select_for_update().get_or_create(
                invoice_series=invoice_series,
            )
            counter.last_number = F("last_number") + 1
            counter.save()
            counter.refresh_from_db()
            return counter.last_number

    @classmethod
    def get_or_create_number(
        cls, job_card: JobCard, invoice_series: str, invoice_type: str, category: str
    ) -> int:
        """
        If an invoice of the same spec already exists on this job_card,
        return its number; otherwise allocate a fresh one.
        """
        existing = cls.objects.filter(
            job_card=job_card,
            invoice_series=invoice_series,
            invoice_type=invoice_type,
            category=category,
        ).first()
        if existing:
            return existing.invoice_number

        return cls._next_number(invoice_series, invoice_type)

    @classmethod
    def get_or_create_number(
        cls, job_card: JobCard, invoice_series: str, category: str = None
    ) -> int:
        # customer bucket (quotes + all customer invoices)
        if category in (None, "", "customer"):
            existing = cls.objects.filter(
                job_card=job_card, invoice_series=invoice_series, invoice_type="quote"
            ).first()
            if existing:
                return existing.invoice_number
            return cls._next_number(invoice_series)

        # insurance bucket
        existing_ins = cls.objects.filter(
            job_card=job_card, invoice_series=invoice_series, category="insurance"
        ).first()
        if existing_ins:
            return existing_ins.invoice_number
        return cls._next_number(invoice_series)
