# yourapp/models.py
from django.db import models
from django.core.validators import MinValueValidator


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
    calling_status = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return f"{self.car_number} ({self.car_make} {self.car_model})"


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
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return f"TempCar for {self.car.car_number} (job {self.job_card_id})"
