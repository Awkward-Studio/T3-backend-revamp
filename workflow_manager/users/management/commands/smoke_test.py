from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from rest_framework.test import APIClient


class Command(BaseCommand):
    help = "Run manage.py check and hit a simple unauthenticated API route."

    def handle(self, *args, **options):
        self.stdout.write("Running `manage.py check`...")
        call_command("check")

        client = APIClient()
        # users/urls.py mounts LabelListCreate at: "labels/"
        # workflow_manager/urls.py mounts users under: "api/"
        url = "/api/labels/"
        self.stdout.write(f"Calling smoke endpoint: GET {url}")

        resp = client.get(url, format="json")
        if resp.status_code != 200:
            raise CommandError(
                f"Smoke endpoint failed: GET {url} returned {resp.status_code}: {resp.content!r}"
            )

        self.stdout.write(self.style.SUCCESS(f"Smoke endpoint OK: {resp.status_code}"))

