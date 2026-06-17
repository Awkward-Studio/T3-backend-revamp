import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from users.models import Role, RoleName
from vehicle_management.models import Car, CustomerPortal, TempCar

from jobcards.models import JobCard


class ParallelDepartmentVisibilityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()

        self.parts_role, _ = Role.objects.get_or_create(name=RoleName.PARTS)
        self.biller_role, _ = Role.objects.get_or_create(name=RoleName.BILLER)
        self.mechanic_role, _ = Role.objects.get_or_create(name=RoleName.MECHANIC)

        self.parts_user = self.user_model.objects.create_user(
            username="parts",
            email="parts@example.com",
            password="password123",
        )
        self.parts_user.roles.add(self.parts_role)

        self.biller_user = self.user_model.objects.create_user(
            username="biller",
            email="biller@example.com",
            password="password123",
        )
        self.biller_user.roles.add(self.biller_role)

        self.mechanic_one = self.user_model.objects.create_user(
            username="mechanic1",
            email="mechanic1@example.com",
            password="password123",
        )
        self.mechanic_one.roles.add(self.mechanic_role)

        self.mechanic_two = self.user_model.objects.create_user(
            username="mechanic2",
            email="mechanic2@example.com",
            password="password123",
        )
        self.mechanic_two.roles.add(self.mechanic_role)

        self.approved_jobcard = self._create_jobcard(
            car_id="JC-APPROVED",
            car_number="MH01AA0001",
            workflow_status=JobCard.WorkflowStatus.CUSTOMER_APPROVED,
            assigned_technician_id=str(self.mechanic_one.pk),
        )
        self.partial_jobcard = self._create_jobcard(
            car_id="JC-PARTIAL",
            car_number="MH01AA0002",
            workflow_status=JobCard.WorkflowStatus.CUSTOMER_PARTIALLY_APPROVED,
            assigned_technician_id=str(self.mechanic_one.pk),
        )
        self.other_mechanic_jobcard = self._create_jobcard(
            car_id="JC-OTHER-MECH",
            car_number="MH01AA0003",
            workflow_status=JobCard.WorkflowStatus.CUSTOMER_APPROVED,
            assigned_technician_id=str(self.mechanic_two.pk),
        )
        self.waiting_jobcard = self._create_jobcard(
            car_id="JC-WAITING",
            car_number="MH01AA0004",
            workflow_status=JobCard.WorkflowStatus.WAITING_CUSTOMER_APPROVAL,
            assigned_technician_id=str(self.mechanic_one.pk),
        )

    def _create_jobcard(
        self,
        *,
        car_id,
        car_number,
        workflow_status,
        assigned_technician_id="",
        job_card_status=0,
    ):
        return JobCard.objects.create(
            car_id=car_id,
            car_number=car_number,
            job_card_status=job_card_status,
            customer_name="Test Customer",
            customer_phone="9999999999",
            workflow_status=workflow_status,
            assigned_technician_id=assigned_technician_id,
            job_card_number=None,
        )

    def test_parts_dashboard_receives_jobcards_immediately_after_customer_approval(
        self,
    ):
        self.client.force_authenticate(user=self.parts_user)

        response = self.client.get("/api/compat/jobcards/")

        self.assertEqual(response.status_code, 200)
        returned_ids = {document["$id"] for document in response.data["documents"]}

        self.assertIn(str(self.approved_jobcard.pk), returned_ids)
        self.assertIn(str(self.partial_jobcard.pk), returned_ids)
        self.assertIn(str(self.other_mechanic_jobcard.pk), returned_ids)
        self.assertNotIn(str(self.waiting_jobcard.pk), returned_ids)

    def test_biller_can_open_customer_approved_jobcard_before_mechanic_completion(self):
        self.client.force_authenticate(user=self.biller_user)

        approved_response = self.client.get(
            f"/api/compat/jobcards/{self.approved_jobcard.pk}/"
        )
        waiting_response = self.client.get(
            f"/api/compat/jobcards/{self.waiting_jobcard.pk}/"
        )

        self.assertEqual(approved_response.status_code, 200)
        self.assertEqual(waiting_response.status_code, 403)
        self.assertEqual(
            waiting_response.data["error"],
            "This vehicle is not available for your role yet.",
        )

    def test_mechanic_dashboard_remains_limited_to_assigned_vehicles(self):
        self.client.force_authenticate(user=self.mechanic_one)

        list_response = self.client.get("/api/compat/mechanic/jobcards/")
        own_detail_response = self.client.get(
            f"/api/compat/jobcards/{self.approved_jobcard.pk}/"
        )
        other_detail_response = self.client.get(
            f"/api/compat/jobcards/{self.other_mechanic_jobcard.pk}/"
        )

        self.assertEqual(list_response.status_code, 200)
        returned_ids = {document["$id"] for document in list_response.data["documents"]}

        self.assertIn(str(self.approved_jobcard.pk), returned_ids)
        self.assertIn(str(self.partial_jobcard.pk), returned_ids)
        self.assertNotIn(str(self.other_mechanic_jobcard.pk), returned_ids)
        self.assertNotIn(str(self.waiting_jobcard.pk), returned_ids)

        self.assertEqual(own_detail_response.status_code, 200)
        self.assertEqual(other_detail_response.status_code, 403)
        self.assertEqual(
            other_detail_response.data["error"],
            "You can only access vehicles assigned to you.",
        )


class AccessoriesPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()

        self.service_role, _ = Role.objects.get_or_create(name=RoleName.SERVICE)
        self.biller_role, _ = Role.objects.get_or_create(name=RoleName.BILLER)

        self.service_user = self.user_model.objects.create_user(
            username="service-accessories",
            email="service-accessories@example.com",
            password="password123",
        )
        self.service_user.roles.add(self.service_role)

        self.biller_user = self.user_model.objects.create_user(
            username="biller-accessories",
            email="biller-accessories@example.com",
            password="password123",
        )
        self.biller_user.roles.add(self.biller_role)

        self.jobcard = JobCard.objects.create(
            car_id="JC-ACCESSORIES",
            car_number="MH01CC0001",
            job_card_status=0,
            customer_name="Accessory Customer",
            customer_phone="9999999997",
            workflow_status=JobCard.WorkflowStatus.CUSTOMER_APPROVED,
            accessories=["Spare Wheel"],
            service_advisor_id=self.service_user.email,
            job_card_number=None,
        )

    def test_service_advisor_can_update_accessories(self):
        self.client.force_authenticate(user=self.service_user)

        response = self.client.patch(
            f"/api/compat/jobcards/{self.jobcard.pk}/",
            {"accessories": ["Spare Wheel", "Tool Kit", "Charger"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.jobcard.refresh_from_db()
        self.assertEqual(
            self.jobcard.accessories, ["Spare Wheel", "Tool Kit", "Charger"]
        )
        self.assertEqual(
            response.data["accessories"],
            ["Spare Wheel", "Tool Kit", "Charger"],
        )

    def test_non_service_user_cannot_update_accessories(self):
        self.client.force_authenticate(user=self.biller_user)

        response = self.client.patch(
            f"/api/compat/jobcards/{self.jobcard.pk}/",
            {"accessories": ["First Aid Kit"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["error"],
            "Only service advisors can add or edit accessories.",
        )
        self.jobcard.refresh_from_db()
        self.assertEqual(self.jobcard.accessories, ["Spare Wheel"])


class CustomerPortalAccessoriesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.car = Car.objects.create(
            car_number="MH01DD0001",
            car_make="Tata",
            car_model="Nexon",
            customer_name="Portal Customer",
            customer_phone="9999999996",
        )
        self.temp_car = TempCar.objects.create(
            car=self.car,
            purpose_of_visit_and_advisors=[
                {
                    "description": "General Service",
                    "advisorEmail": "advisor@example.com",
                }
            ],
        )
        self.jobcard = JobCard.objects.create(
            car_id="JC-PORTAL-ACCESSORIES",
            temp_car=self.temp_car,
            car_number=self.car.car_number,
            job_card_status=0,
            customer_name=self.car.customer_name,
            customer_phone=self.car.customer_phone,
            purpose_of_visit="General Service",
            workflow_status=JobCard.WorkflowStatus.JOB_CARD_CREATED,
            accessories=["Spare Wheel", "Tool Kit"],
            job_card_number=None,
        )
        CustomerPortal.objects.create(car=self.car)

    def test_customer_portal_includes_current_visit_accessories(self):
        response = self.client.post(
            "/api/compat/portal/",
            {"licensePlate": self.car.car_number},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["currentVehicleStatus"]["accessories"],
            ["Spare Wheel", "Tool Kit"],
        )


class InsuranceDetailsPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()

        self.biller_role, _ = Role.objects.get_or_create(name=RoleName.BILLER)
        self.security_role, _ = Role.objects.get_or_create(name=RoleName.SECURITY)

        self.biller_user = self.user_model.objects.create_user(
            username="biller-insurance",
            email="biller-insurance@example.com",
            password="password123",
        )
        self.biller_user.roles.add(self.biller_role)

        self.security_user = self.user_model.objects.create_user(
            username="security-insurance",
            email="security-insurance@example.com",
            password="password123",
        )
        self.security_user.roles.add(self.security_role)

        self.open_jobcard = JobCard.objects.create(
            car_id="JC-INS-OPEN",
            car_number="MH01BB0001",
            job_card_status=5,
            customer_name="Insurance Customer",
            customer_phone="9999999999",
            workflow_status=JobCard.WorkflowStatus.POST_DELIVERY_COMPLETED,
            insurance_details=self._insurance_details_payload(),
            job_card_number=None,
        )
        self.exited_jobcard = JobCard.objects.create(
            car_id="JC-INS-EXIT",
            car_number="MH01BB0002",
            job_card_status=7,
            customer_name="Exited Customer",
            customer_phone="9999999998",
            workflow_status=JobCard.WorkflowStatus.VEHICLE_COLLECTED,
            insurance_details=self._insurance_details_payload(),
            job_card_number=None,
        )

    def _insurance_details_payload(self, **overrides):
        payload = {
            "policyProvider": "ICICI Lombard",
            "policyNumber": "POL-001",
            "surveyorName": "Rohit Sharma",
            "surveyorCompany": "Survey Co",
            "surveyorPhoneNumber": "9999999999",
            "surveyStatus": "Pending",
        }
        payload.update(overrides)
        return json.dumps(payload)

    def test_only_biller_can_update_surveyor_details_and_status(self):
        self.client.force_authenticate(user=self.security_user)

        response = self.client.patch(
            f"/api/compat/jobcards/{self.open_jobcard.pk}/",
            {
                "insuranceDetails": self._insurance_details_payload(
                    surveyorName="Updated Surveyor",
                    surveyStatus="Done",
                )
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["error"],
            "Only billers can update insurance surveyor details or survey status.",
        )

    def test_biller_can_update_surveyor_details_before_vehicle_exit(self):
        self.client.force_authenticate(user=self.biller_user)

        response = self.client.patch(
            f"/api/compat/jobcards/{self.open_jobcard.pk}/",
            {
                "insuranceDetails": self._insurance_details_payload(
                    surveyorName="Aman Surveyor",
                    surveyorCompany="Claims India",
                    surveyorPhoneNumber="8888888888",
                    surveyStatus="Done",
                )
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.open_jobcard.refresh_from_db()
        payload = json.loads(self.open_jobcard.insurance_details)
        self.assertEqual(payload["surveyorName"], "Aman Surveyor")
        self.assertEqual(payload["surveyorCompany"], "Claims India")
        self.assertEqual(payload["surveyorPhoneNumber"], "8888888888")
        self.assertEqual(payload["surveyStatus"], "Done")

    def test_biller_can_update_survey_status_after_exit_but_not_surveyor_details(self):
        self.client.force_authenticate(user=self.biller_user)

        denied_response = self.client.patch(
            f"/api/compat/jobcards/{self.exited_jobcard.pk}/",
            {
                "insuranceDetails": self._insurance_details_payload(
                    surveyorName="Post Exit Surveyor"
                )
            },
            format="json",
        )

        self.assertEqual(denied_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            denied_response.data["error"],
            "Surveyor details cannot be edited after vehicle exit.",
        )

        allowed_response = self.client.patch(
            f"/api/compat/jobcards/{self.exited_jobcard.pk}/",
            {
                "insuranceDetails": self._insurance_details_payload(
                    surveyStatus="Not Done"
                )
            },
            format="json",
        )

        self.assertEqual(allowed_response.status_code, status.HTTP_200_OK)
        self.exited_jobcard.refresh_from_db()
        payload = json.loads(self.exited_jobcard.insurance_details)
        self.assertEqual(payload["surveyorName"], "Rohit Sharma")
        self.assertEqual(payload["surveyStatus"], "Not Done")
