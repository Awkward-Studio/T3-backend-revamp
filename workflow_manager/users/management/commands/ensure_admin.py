from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from users.models import Role, RoleName


class Command(BaseCommand):
    help = "Create the default admin user if it does not already exist"

    def handle(self, *args, **options):
        email = "admin@example.com"
        password = "changeme"
        User = get_user_model()

        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            self.stdout.write(f"Admin user already exists: {email}")
            return

        admin_user = User.objects.create_superuser(
            username=email,
            email=email,
            password=password,
        )
        admin_role, _ = Role.objects.get_or_create(name=RoleName.ADMIN)
        admin_user.roles.add(admin_role)

        self.stdout.write(self.style.SUCCESS(f"Created admin user: {email}"))
