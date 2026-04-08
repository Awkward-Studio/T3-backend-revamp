# yourapp/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser


class RoleName:
    ADMIN = "admin"
    SERVICE = "service"
    BILLER = "biller"
    PARTS = "parts"
    SECURITY = "security"
    CALLER = "caller"

    ALL = (
        ADMIN,
        SERVICE,
        BILLER,
        PARTS,
        SECURITY,
        CALLER,
    )


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

    @classmethod
    def role_names(cls):
        return RoleName.ALL


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

    def has_role(self, role_name):
        return self.roles.filter(name=role_name).exists()

    def has_any_role(self, role_names):
        return self.roles.filter(name__in=role_names).exists()

    def get_primary_role(self):
        role = self.roles.order_by("id").first()
        return role.name if role else None

    def set_single_role(self, role_name):
        role = Role.objects.get(name=role_name)
        self.roles.set([role])


