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

    def make_completed_jobcard(self, car, completed_days_ago, number=1):
        completed_at = timezone.now() - timedelta(days=completed_days_ago)
        jobcard = JobCard.objects.create(
            car_id=f"job-{number}",
            car_number=car.car_number,
            job_card_status=1,
            customer_name=car.customer_name,
            customer_phone=car.customer_phone,
            job_card_number=number,
            post_delivery_completed_at=completed_at,
        )
        return jobcard

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
        self.assertEqual(fallback["car_number"], "KA03CC0003")
        self.assertEqual(fallback["period_date"], fallback_car.created_at.date())

    def test_upload_keeps_same_phone_for_different_cars(self):
        self.make_car("KA01AA0001", "9876543210", 100, "First Customer")
        self.make_car("KA02BB0002", "+91 98765 43210", 110, "Duplicate")
        self.make_car("KA03CC0003", "123", 120, "Invalid")
        self.make_car("KA04DD0004", "9999999999", 10, "Too Recent")

        leads, invalid = eligible_leads(90)

        self.assertEqual(invalid, 1)
        self.assertEqual(len(leads), 2)
        self.assertEqual(
            leads[0]["payload"],
            {"name": "Duplicate", "phone": "919876543210"},
        )
        self.assertEqual(
            {lead["car_number"] for lead in leads},
            {"KA01AA0001", "KA02BB0002"},
        )

    def test_latest_completed_service_defines_caller_period(self):
        car = self.make_car("KA01AA0001", "9876543210", 200)
        self.make_completed_jobcard(car, 20)

        self.assertEqual(caller_car_records(timezone.now() - timedelta(days=90)), [])

        JobCard.objects.filter(car_number=car.car_number).update(
            post_delivery_completed_at=timezone.now() - timedelta(days=100)
        )
        records = caller_car_records(timezone.now() - timedelta(days=90))
        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["period_date"],
            (timezone.now() - timedelta(days=100)).date(),
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

    @patch.dict("os.environ", {
        "TELECRM_ENTERPRISE_ID": "enterprise",
        "TELECRM_ASYNC_TOKEN": "token",
    })
    @patch("workflow_manager.telecrm_service._request", return_value={"status": "QUEUED"})
    def test_same_phone_later_service_period_is_queued(self, request):
        car = self.make_car("KA01AA0001", "9876543210", 200)
        jobcard = self.make_completed_jobcard(car, 100)
        first = sync_eligible_leads(90)

        JobCard.objects.filter(pk=jobcard.pk).update(
            post_delivery_completed_at=timezone.now() - timedelta(days=99)
        )
        second = sync_eligible_leads(90)

        self.assertEqual(first["queued"], 1)
        self.assertEqual(second["queued"], 1)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(TelecrmLeadSync.objects.count(), 2)

    def test_lead_snapshot_is_one_bounded_request(self):
        client = TelecrmSyncClient()
        calls = []
        client.search = lambda **kwargs: calls.append(kwargs) or {
            "data": [{"fields": {"phone": str(index)}} for index in range(100)],
            "total_count": 250,
        }

        leads, total = client.lead_snapshot()

        self.assertEqual(len(leads), 100)
        self.assertEqual(total, 250)
        self.assertEqual(calls, [{"limit": 100}])

    @patch("workflow_manager.telecrm_service.TelecrmSyncClient")
    def test_dashboard_returns_partial_breakdown_warning(self, client_class):
        client = client_class.return_value
        client.lead_snapshot.return_value = (
            [{"fields": {"status": "Fresh", "assignee": "agent@example.com"}}],
            2,
        )
        client.team_snapshot.return_value = ([], 0)
        client.pipeline.return_value = {"leadStages": []}
        client.count.return_value = 3

        dashboard = build_dashboard(30)

        self.assertEqual(dashboard["summary"]["totalLeads"], 2)
        self.assertEqual(dashboard["breakdowns"]["status"], {"Fresh": 1})
        self.assertTrue(any("first 1 of 2" in warning for warning in dashboard["warnings"]))
