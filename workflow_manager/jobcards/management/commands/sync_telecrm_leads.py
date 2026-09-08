from django.core.management.base import BaseCommand, CommandError

from workflow_manager.telecrm_service import missing_config, sync_eligible_leads


class Command(BaseCommand):
    help = "Queue the same 90-day-old customer list shown on the Caller page in TeleCRM."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if not options["dry_run"] and missing_config(True):
            raise CommandError("Missing: " + ", ".join(missing_config(True)))
        result = sync_eligible_leads(options["days"], dry_run=options["dry_run"])
        self.stdout.write(self.style.SUCCESS(json_summary(result)))


def json_summary(result):
    return ", ".join(f"{key}={value}" for key, value in result.items() if key != "errors")
