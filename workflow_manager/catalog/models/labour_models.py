import uuid
from django.db import models


class Labour(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    labour_name = models.CharField(max_length=255)
    labour_code = models.CharField(max_length=50, unique=True, blank=True, null=True)
    hsn = models.CharField(max_length=20)
    category = models.CharField(max_length=100, blank=True, null=True)
    mrp = models.DecimalField(max_digits=10, decimal_places=2)
    gst = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    cgst = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    sgst = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.labour_name} ({self.labour_code})"
