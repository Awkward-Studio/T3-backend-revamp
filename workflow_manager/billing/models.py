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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_card = models.ForeignKey(
        JobCard, on_delete=models.CASCADE, related_name="invoices"
    )
    invoice_series = models.CharField(max_length=10, choices=SERIES_CHOICES)
    invoice_type = models.CharField(max_length=50)
    category = models.CharField(max_length=20, blank=True, default="")
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
        return f"{self.invoice_series} {self.invoice_type} [{self.category}] #{self.invoice_number}"

    @classmethod
    def _next_number(cls, invoice_series: str) -> int:
        """
        Atomically bump and return the next number for an invoice series.
        """
        with transaction.atomic():
            counter, _ = InvoiceCounter.objects.select_for_update().get_or_create(
                series=invoice_series,
            )
            counter.last_number = F("last_number") + 1
            counter.save(update_fields=["last_number"])
            counter.refresh_from_db(fields=["last_number"])
            return counter.last_number

    @classmethod
    def get_or_create_number(
        cls,
        job_card: JobCard,
        invoice_series: str,
        invoice_type: str,
        category: str = None,
    ) -> int:
        """
        If an invoice of the same spec already exists on this job_card,
        return its number; otherwise allocate a fresh one.
        """
        # The API stores quote-category as an empty string (see CreateInvoiceView).
        if invoice_type == "quote":
            category = ""
        else:
            category = category or ""

        existing_qs = cls.objects.filter(
            job_card=job_card,
            invoice_series=invoice_series,
            invoice_type=invoice_type,
            category=category,
        )
        existing = existing_qs.first()
        if existing:
            return existing.invoice_number

        # Counter is tracked per invoice_series.
        return cls._next_number(invoice_series)
