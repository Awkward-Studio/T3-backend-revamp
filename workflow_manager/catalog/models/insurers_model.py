import uuid
from django.db import models


class InsuranceProvider(models.Model):
    """
    Stores information about an insurance company/provider.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    insurer = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    gst = models.CharField("GST Number", max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.insurer
