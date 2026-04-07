# yourapp/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser


class Label(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Role(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)
    permissions = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        help_text="Store role permissions as JSON",
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Roles"
        ordering = ["id"]


class CustomUser(AbstractUser):
    # free-form tags
    labels = models.ManyToManyField(Label, blank=True, related_name="users")

    # arbitrary JSON: {"theme":"dark","timezone":"Asia/Kolkata"}
    preferences = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        help_text="Store custom user preferences as JSON",
    )

    roles = models.ManyToManyField(Role, blank=True, related_name="users")


