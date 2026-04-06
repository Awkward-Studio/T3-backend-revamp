import uuid
from django.db import models


class VehilceModel(models.Model):
    """
    A car make and its list of models.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    make = models.CharField(max_length=255)
    models = models.JSONField(
        default=list,
        blank=True,
        help_text="A list of model names, e.g. ['A4','Q5','TT']",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.make} ({len(self.models)} models)"
