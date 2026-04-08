from django.core.management.base import BaseCommand
from users.models import Role


class Command(BaseCommand):
    help = "Seed default roles"

    def handle(self, *args, **kwargs):
        roles = ["admin", "service", "biller", "parts", "security", "caller"]

        for role in roles:
            Role.objects.get_or_create(name=role)

        self.stdout.write(self.style.SUCCESS("Roles seeded successfully"))