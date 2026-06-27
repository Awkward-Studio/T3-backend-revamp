import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F
from jobcards.models import JobCard
from vehicle_management.models import Car


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
    wallet_transaction = models.OneToOneField(
        "WalletTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice",
    )
    invoice_series = models.CharField(max_length=10, choices=SERIES_CHOICES)
    invoice_type = models.CharField(max_length=50)
    category = models.CharField(max_length=20, blank=True, default="")
    invoice_number = models.PositiveIntegerField()
    invoice_code = models.CharField(max_length=50, blank=True)
    car_number = models.CharField(max_length=50, blank=True)
    is_updated = models.BooleanField(default=False)
    is_insurance_invoice = models.BooleanField(default=False)
    inventory_consumed_at = models.DateTimeField(blank=True, null=True)
    invoice_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    wallet_credit_used = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    final_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    apply_gst = models.BooleanField(default=True)
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

        if normalized_type in cls._customer_invoice_types() or normalized_category in {
            "",
            "customer",
        }:
            candidate_categories = ["", "Customer", "customer"]
            customer_qs = qs.filter(category__in=candidate_categories).order_by(
                "created_at", "invoice_number"
            )
            for invoice in customer_qs:
                if (
                    cls._normalized_label(invoice.invoice_type)
                    in cls._customer_invoice_types()
                ):
                    return invoice
            return None

        exact_qs = qs.filter(category=category or "").order_by(
            "created_at", "invoice_number"
        )
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

        if normalized_type in cls._customer_invoice_types() or normalized_category in {
            "",
            "customer",
        }:
            category = ""
        else:
            category = category or ""

        existing = cls.find_existing_invoice(
            job_card=job_card,
            invoice_series=invoice_series,
            invoice_type=invoice_type,
            category=category,
        )
        if existing:
            return existing.invoice_number

        return cls._next_number(invoice_series)


class CustomerWallet(models.Model):
    car = models.OneToOneField(
        Car,
        on_delete=models.CASCADE,
        related_name="customer_wallet",
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def __str__(self):
        return f"Wallet for {self.car.car_number}"


class WalletTransaction(models.Model):
    class TransactionType(models.TextChoices):
        CREDIT = "CREDIT", "Credit"
        DEBIT = "DEBIT", "Debit"

    wallet = models.ForeignKey(
        CustomerWallet,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reason = models.TextField()
    type = models.CharField(max_length=10, choices=TransactionType.choices)
    created_by = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.type} {self.amount} for {self.wallet.car.car_number}"
