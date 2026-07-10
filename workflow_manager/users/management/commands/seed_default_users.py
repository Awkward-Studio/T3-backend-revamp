from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from users.models import Role, RoleName


DEFAULT_PASSWORD = "Changeme"
DEFAULT_ADMIN_EMAIL = "admin@example.com"


class Command(BaseCommand):
    help = "Create one default user for each role if missing"

    def handle(self, *args, **options):
        admin_email = DEFAULT_ADMIN_EMAIL
        admin_password = DEFAULT_PASSWORD

        users = [
            # Primary admin
            {
                "email": admin_email,
                "password": admin_password,
                "role": RoleName.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
            {"email": "service@example.com", "password": DEFAULT_PASSWORD, "role": RoleName.SERVICE},
            {"email": "biller@example.com", "password": DEFAULT_PASSWORD, "role": RoleName.BILLER},
            {"email": "parts@example.com", "password": DEFAULT_PASSWORD, "role": RoleName.PARTS},
            {"email": "security@example.com", "password": DEFAULT_PASSWORD, "role": RoleName.SECURITY},
            {"email": "caller@example.com", "password": DEFAULT_PASSWORD, "role": RoleName.CALLER},
            {"email": "mechanic@example.com", "password": DEFAULT_PASSWORD, "role": RoleName.MECHANIC},
        ]

        User = get_user_model()
        created_count = 0
        updated_count = 0

        with transaction.atomic():
            roles = {
                role_name: Role.objects.get_or_create(name=role_name)[0]
                for role_name in RoleName.ALL
            }

            for user_config in users:
                email = user_config["email"]
                role_name = user_config["role"]

                user = (
                    User.objects.filter(email__iexact=email).first()
                    or User.objects.filter(username__iexact=email).first()
                )

                if user is None:
                    user = User.objects.create_user(
                        username=email,
                        email=email,
                        password=user_config["password"],
                    )
                    created_count += 1
                else:
                    updated_count += 1

                user.username = email
                user.email = email
                user.set_password(user_config["password"])
                user.is_active = True
                user.is_staff = user_config.get("is_staff", False)
                user.is_superuser = user_config.get("is_superuser", False)
                user.save()

                user.roles.set([roles[role_name]])

        self.stdout.write(
            self.style.SUCCESS(
                f"Default users ready. Created: {created_count}. Existing updated: {updated_count}."
            )
        )
