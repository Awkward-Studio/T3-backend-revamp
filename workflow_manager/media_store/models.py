import os
import uuid

from django.db import models


def asset_upload_to(instance, filename):
    ext = os.path.splitext(filename)[1] or ""
    return f"{instance.kind}/{instance.id}{ext}"


class UploadedAsset(models.Model):
    KIND_IMAGE = "image"
    KIND_INVOICE = "invoice"
    KIND_PDF = "pdf"

    KIND_CHOICES = [
        (KIND_IMAGE, "Image"),
        (KIND_INVOICE, "Invoice"),
        (KIND_PDF, "PDF"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    file_url = models.URLField(null=True, blank=True)
    # file = models.FileField(upload_to=asset_upload_to)
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.kind}:{self.original_name or self.file.name}"
