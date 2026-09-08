from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from jobcards.models import JobCard, TelecrmLeadSync
from vehicle_management.models import Car
from workflow_manager.caller_service import caller_car_records
from workflow_manager.telecrm_service import (
    TelecrmSyncClient,
    build_dashboard,
    eligible_leads,
    normalize_phone,
    sync_eligible_leads,
)


class TelecrmLeadSyncTests(TestCase):
    def make_car(self, number, phone, age_days, name="Test Customer"):
        car = Car.objects.create(
            car_number=number,
            customer_name=name,
            customer_phone=phone,
        )
        Car.objects.filter(pk=car.pk).update(
            created_at=timezone.now() - timedelta(days=age_days)
        )
        car.refresh_from_db()
        return car

    def test_phone_normalization(self):
        self.assertEqual(normalize_phone("98765 43210"), "919876543210")
        self.assertEqual(normalize_phone("+91-98765-43210"), "919876543210")
        self.assertEqual(normalize_phone("123"), "")

    def test_caller_records_apply_age_cutoff_and_jobcard_fallback(self):
        old_car = self.make_car("KA01AA0001", "9876543210", 100)
        self.make_car("KA02BB0002", "9999999999", 10)
        fallback_car = self.make_car("KA03CC0003", "", 120, name="")
        jobcard = JobCard.objects.create(
            car_id="legacy-car",
            car_number=fallback_car.car_number,
            job_card_status=1,
            customer_name="Fallback Customer",
            customer_phone="9123456789",
            job_card_number=1,
        )
        JobCard.objects.filter(pk=jobcard.pk).update(
            created_at=timezone.now() - timedelta(days=100)
        )

        records = caller_car_records(timezone.now() - timedelta(days=90))

        self.assertEqual(
            {record["car"].pk for record in records},
            {old_car.pk, fallback_car.pk},
        )
        fallback = next(record for record in records if record["car"] == fallback_car)
        self.assertEqual(fallback["customer_name"], "Fallback Customer")
        self.assertEqual(fallback["customer_phone"], "9123456789")

    def test_upload_uses_only_unique_valid_caller_page_leads(self):
        self.make_car("KA01AA0001", "9876543210", 100, "First Customer")
        self.make_car("KA02BB0002", "+91 98765 43210", 110, "Duplicate")
        self.make_car("KA03CC0003", "123", 120, "Invalid")
        self.make_car("KA04DD0004", "9999999999", 10, "Too Recent")

        leads, invalid = eligible_leads(90)

        self.assertEqual(invalid, 1)
        self.assertEqual(len(leads), 1)
        self.assertEqual(
            leads[0]["payload"],
            {"name": "Duplicate", "phone": "919876543210"},
        )

    @patch.dict("os.environ", {
        "TELECRM_ENTERPRISE_ID": "enterprise",
        "TELECRM_ASYNC_TOKEN": "token",
    })
    @patch("workflow_manager.telecrm_service._request", return_value={"status": "QUEUED"})
    def test_identical_payload_is_not_queued_twice(self, request):
        self.make_car("KA01AA0001", "9876543210", 100)

        first = sync_eligible_leads(90)
        second = sync_eligible_leads(90)

        self.assertEqual(first["queued"], 1)
        self.assertEqual(second["unchanged"], 1)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(TelecrmLeadSync.objects.count(), 1)

    @patch.dict("os.environ", {"TELECRM_DASHBOARD_MAX_LEADS": "100"})
    def test_lead_download_is_bounded(self):
        client = TelecrmSyncClient()
        client.search = lambda **_kwargs: {
            "data": [{"fields": {"phone": str(index)}} for index in range(100)],
            "total_count": 250,
        }

        leads, total = client.all_leads()

        self.assertEqual(len(leads), 100)
        self.assertEqual(total, 250)

    @patch("workflow_manager.telecrm_service.TelecrmSyncClient")
    def test_dashboard_returns_partial_breakdown_warning(self, client_class):
        client = client_class.return_value
        client.all_leads.return_value = (
            [{"fields": {"status": "Fresh", "assignee": "agent@example.com"}}],
            2,
        )
        client.team.return_value = []
        client.pipeline.return_value = {"leadStages": []}
        client.count.return_value = 3

        dashboard = build_dashboard(30)

        self.assertEqual(dashboard["summary"]["totalLeads"], 2)
        self.assertEqual(dashboard["breakdowns"]["status"], {"Fresh": 1})
        self.assertTrue(any("first 1 of 2" in warning for warning in dashboard["warnings"]))
