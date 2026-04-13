import uuid

from django.db import models


class HistoryEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    object_id = models.CharField(max_length=100, db_index=True)
    object_type = models.CharField(max_length=50, db_index=True)
    operation_type = models.CharField(max_length=30)
    user_id = models.CharField(max_length=100, blank=True)
    user_email = models.EmailField(blank=True)
    user_name = models.CharField(max_length=255, blank=True)
    history = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.object_type}:{self.object_id}:{self.operation_type}"
