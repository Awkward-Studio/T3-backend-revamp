import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from users.models import Role, RoleName


class Command(BaseCommand):
    help = "Create the default admin user if it does not already exist"

    def handle(self, *args, **options):
        email = os.getenv("ADMIN_EMAIL", "admin@example.com")
        password = os.getenv("ADMIN_PASSWORD") or os.getenv("SEED_USER_PASSWORD", "Example@2026")
        reset_password = os.getenv("RESET_ADMIN_PASSWORD", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        User = get_user_model()

        admin_user = (
            User.objects.filter(email__iexact=email).first()
            or User.objects.filter(username__iexact=email).first()
        )
        created = admin_user is None

        if created:
            admin_user = User(username=email, email=email)

        admin_user.username = email
        admin_user.email = email
        admin_user.is_active = True
        admin_user.is_staff = True
        admin_user.is_superuser = True
        if created or reset_password:
            admin_user.set_password(password)
        admin_user.save()

        admin_role, _ = Role.objects.get_or_create(name=RoleName.ADMIN)
        admin_user.roles.add(admin_role)

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} admin user: {email}"))
