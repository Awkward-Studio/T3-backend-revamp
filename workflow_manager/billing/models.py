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
    last_number = models.PositiveIntegerField(default=1000)

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

    @staticmethod
    def _normalized_label(value) -> str:
        return " ".join(str(value or "").replace("-", " ").split()).strip().lower()

    @classmethod
    def _customer_invoice_types(cls) -> set:
        return {"quote", "pro forma invoice", "tax invoice"}

    @classmethod
    def find_existing_invoice(
        cls,
        job_card: JobCard,
        invoice_series: str,
        invoice_type: str,
        category: str = None,
    ):
        """
        Resolve the canonical invoice for a job card.

        Quote, Pro-Forma Invoice, and Tax Invoice are treated as one customer
        invoice family so any of them can find the same existing record.
        """
        normalized_type = cls._normalized_label(invoice_type)
        normalized_category = cls._normalized_label(category)
        qs = cls.objects.filter(job_card=job_card, invoice_series=invoice_series)

        if normalized_type in cls._customer_invoice_types() or normalized_category in {"", "customer"}:
            candidate_categories = ["", "Customer", "customer"]
            customer_qs = qs.filter(category__in=candidate_categories).order_by("created_at", "invoice_number")
            for invoice in customer_qs:
                if cls._normalized_label(invoice.invoice_type) in cls._customer_invoice_types():
                    return invoice
            return None

        exact_qs = qs.filter(category=category or "").order_by("created_at", "invoice_number")
        for invoice in exact_qs:
            if cls._normalized_label(invoice.invoice_type) == normalized_type:
                return invoice
        return None

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
        normalized_type = cls._normalized_label(invoice_type)
        normalized_category = cls._normalized_label(category)

        # Customer quote/pro-forma/tax invoices share the same logical invoice.
        if normalized_type in cls._customer_invoice_types() or normalized_category in {"", "customer"}:
            category = ""
        else:
            category = category or ""
        print("job card", job_card)
        print("invoice type is", invoice_type)
        print("Invoice series is", invoice_series)
        print("cls", cls)
        existing = cls.find_existing_invoice(
            job_card=job_card,
            invoice_series=invoice_series,
            invoice_type=invoice_type,
            category=category,
        )
        existing_qs = cls.objects.filter(pk=existing.pk) if existing else cls.objects.none()
        print("existing", existing_qs)
        if existing:
            return existing.invoice_number

        # Counter is tracked per invoice_series.
        return cls._next_number(invoice_series)
