from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from jobcards.models import JobCard, TelecrmLeadSync
from workflow_manager.telecrm_service import eligible_leads, normalize_phone, sync_eligible_leads


class TelecrmLeadSyncTests(TestCase):
    def make_jobcard(self, car, phone, completed_at, number):
        return JobCard.objects.create(
            car_id=f"car-{number}",
            car_number=car,
            job_card_status=1,
            customer_name="Test Customer",
            customer_phone=phone,
            job_card_number=number,
            post_delivery_completed_at=completed_at,
            workflow_status=JobCard.WorkflowStatus.POST_DELIVERY_COMPLETED,
        )

    def test_phone_normalization(self):
        self.assertEqual(normalize_phone("98765 43210"), "919876543210")
        self.assertEqual(normalize_phone("+91-98765-43210"), "919876543210")
        self.assertEqual(normalize_phone("123"), "")

    def test_only_latest_service_per_vehicle_decides_eligibility(self):
        now = timezone.now()
        self.make_jobcard("KA 01 AA 0001", "9876543210", now - timedelta(days=120), 1)
        self.make_jobcard("KA01AA0001", "9876543210", now - timedelta(days=10), 2)
        self.make_jobcard("KA 02 BB 0002", "9876543210", now - timedelta(days=100), 3)

        leads, invalid = eligible_leads(90)

        self.assertEqual(invalid, 0)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["payload"]["phone"], "919876543210")

    @patch.dict("os.environ", {
        "TELECRM_ENTERPRISE_ID": "enterprise",
        "TELECRM_ASYNC_TOKEN": "token",
    })
    @patch("workflow_manager.telecrm_service._request", return_value={"status": "QUEUED"})
    def test_identical_payload_is_not_queued_twice(self, request):
        self.make_jobcard("KA01AA0001", "9876543210", timezone.now() - timedelta(days=100), 1)

        first = sync_eligible_leads(90)
        second = sync_eligible_leads(90)

        self.assertEqual(first["queued"], 1)
        self.assertEqual(second["unchanged"], 1)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(TelecrmLeadSync.objects.count(), 1)
