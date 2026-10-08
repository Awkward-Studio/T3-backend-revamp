import uuid
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Car(models.Model):
    car_number = models.CharField(max_length=100, unique=True)
    car_make = models.CharField(max_length=100, blank=True)
    car_model = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=200, blank=True)
    purpose_of_visit = models.CharField(max_length=200, blank=True)
    all_job_cards = models.JSONField(default=list, blank=True)
    cars_table_id = models.CharField(max_length=100, blank=True, null=True)
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    customer_address = models.CharField(max_length=300, blank=True)
    purpose_of_visit_and_advisors = models.JSONField(default=list, blank=True)
    customer_email = models.EmailField(blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    anniversary_date = models.DateField(blank=True, null=True)
    insurance_policy_expiry_date = models.DateField(blank=True, null=True)
    calling_status = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.car_number} ({self.car_make} {self.car_model})"


class CustomerPortal(models.Model):
    car = models.OneToOneField(
        Car, on_delete=models.CASCADE, related_name="customer_portal"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"CustomerPortal for {self.car.car_number}"


class TempCar(models.Model):
    """
    A working‐copy of Car for in‐flight jobcard operations.
    Destroy when job cards are closed.
    """

    # link back to permanent record:
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="temp_versions")

    # operational fields:
    job_card_id = models.CharField(max_length=100, blank=True)
    car_status = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    cars_table_id = models.CharField(max_length=100, blank=True)

    # copy‐over of visit/advisor info so you can tweak it in TempCar
    purpose_of_visit_and_advisors = models.JSONField(default=list, blank=True)
    all_job_card_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"TempCar for {self.car.car_number} (job {self.job_card_id})"


class DriverAssignment(models.Model):
    class AssignmentType(models.TextChoices):
        PICKUP = "PICKUP", "Pickup"
        DROP = "DROP", "Drop"

    class AssignmentStatus(models.TextChoices):
        ASSIGNED = "ASSIGNED", "Assigned"
        PICKED_UP = "PICKED_UP", "Picked Up"
        DROP_STARTED = "DROP_STARTED", "Drop Started"
        DROPPED = "DROPPED", "Dropped"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment_type = models.CharField(
        max_length=20,
        choices=AssignmentType.choices,
        default=AssignmentType.PICKUP,
    )
    status = models.CharField(
        max_length=20,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.ASSIGNED,
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_assignments",
    )
    car = models.ForeignKey(
        Car,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_assignments",
    )
    car_number = models.CharField(max_length=100, blank=True)
    car_make = models.CharField(max_length=100, blank=True)
    car_model = models.CharField(max_length=100, blank=True)
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    customer_address = models.TextField(blank=True)
    customer_email = models.EmailField(blank=True)

    temp_car = models.ForeignKey(
        TempCar,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_assignments",
    )
    job_card = models.ForeignKey(
        "jobcards.JobCard",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_assignments",
    )

    pickup_location = models.CharField(max_length=300, blank=True)
    drop_location = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)

    assigned_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_driver_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        target_car = self.car_number or (self.car.car_number if self.car else "N/A")
        return f"{self.assignment_type} - {target_car} ({self.status})"

    def sync_related_details(self):
        if self.car:
            if not self.car_number:
                self.car_number = self.car.car_number
            if not self.car_make and self.car.car_make:
                self.car_make = self.car.car_make
            if not self.car_model and self.car.car_model:
                self.car_model = self.car.car_model
            if not self.customer_name and self.car.customer_name:
                self.customer_name = self.car.customer_name
            if not self.customer_phone and self.car.customer_phone:
                self.customer_phone = self.car.customer_phone
            if not self.customer_address and self.car.customer_address:
                self.customer_address = self.car.customer_address
            if not self.customer_email and self.car.customer_email:
                self.customer_email = self.car.customer_email
        elif self.job_card:
            if not self.car_number:
                self.car_number = self.job_card.car_number
            if not self.customer_name:
                self.customer_name = self.job_card.customer_name
            if not self.customer_phone:
                self.customer_phone = self.job_card.customer_phone
            if not self.customer_address and self.job_card.customer_address:
                self.customer_address = self.job_card.customer_address
            if not self.customer_email and self.job_card.customer_email:
                self.customer_email = self.job_card.customer_email
            if not self.car:
                self.car = Car.objects.filter(car_number__iexact=self.job_card.car_number).first()
        elif self.car_number and not self.car:
            matched_car = Car.objects.filter(car_number__iexact=self.car_number).first()
            if matched_car:
                self.car = matched_car
                if not self.car_make and matched_car.car_make:
                    self.car_make = matched_car.car_make
                if not self.car_model and matched_car.car_model:
                    self.car_model = matched_car.car_model
                if not self.customer_name and matched_car.customer_name:
                    self.customer_name = matched_car.customer_name
                if not self.customer_phone and matched_car.customer_phone:
                    self.customer_phone = matched_car.customer_phone

    def save(self, *args, **kwargs):
        self.sync_related_details()
        super().save(*args, **kwargs)

    @property
    def total_expenses(self):
        total = self.expenses.aggregate(total=models.Sum("amount"))["total"]
        return total or 0


class DriverExpense(models.Model):
    class ExpenseCategory(models.TextChoices):
        FUEL = "Fuel", "Fuel"
        TOLL = "Toll", "Toll"
        PARKING = "Parking", "Parking"
        OTHER = "Other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(
        DriverAssignment,
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    category = models.CharField(
        max_length=50,
        choices=ExpenseCategory.choices,
        default=ExpenseCategory.OTHER,
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_expenses",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.category}: {self.amount} for {self.assignment_id}"
