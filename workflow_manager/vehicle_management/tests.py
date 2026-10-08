from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from jobcards.models import JobCard
from users.models import CustomUser, Role, RoleName
from vehicle_management.models import (
    Car,
    DriverAssignment,
    DriverExpense,
    TempCar,
)


class DriverPickupDropWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Seed roles
        for r in RoleName.ALL:
            Role.objects.get_or_create(name=r)

        # Admin user
        self.admin = CustomUser.objects.create_user(
            username="admin@t3.com",
            email="admin@t3.com",
            password="password123",
            first_name="Admin",
            last_name="User",
        )
        self.admin.set_single_role(RoleName.ADMIN)

        # Driver 1
        self.driver1 = CustomUser.objects.create_user(
            username="driver1@t3.com",
            email="driver1@t3.com",
            password="password123",
            first_name="Ramesh",
            last_name="Driver",
        )
        self.driver1.set_single_role(RoleName.DRIVER)

        # Driver 2
        self.driver2 = CustomUser.objects.create_user(
            username="driver2@t3.com",
            email="driver2@t3.com",
            password="password123",
            first_name="Suresh",
            last_name="Driver",
        )
        self.driver2.set_single_role(RoleName.DRIVER)

        # Security user
        self.security = CustomUser.objects.create_user(
            username="security@t3.com",
            email="security@t3.com",
            password="password123",
            first_name="Security",
            last_name="Guard",
        )
        self.security.set_single_role(RoleName.SECURITY)

    def test_01_driver_role_and_user_creation(self):
        """Verify driver role exists and user management supports driver role."""
        self.assertTrue(self.driver1.has_role(RoleName.DRIVER))
        self.assertEqual(self.driver1.get_primary_role(), "driver")

        # Test listing users by role via compat view
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/compat/users/?role=driver")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        emails = [u["email"] for u in res.data]
        self.assertIn("driver1@t3.com", emails)
        self.assertIn("driver2@t3.com", emails)

    def test_02_pickup_workflow_and_security_connection(self):
        """Full pickup flow: Admin creates -> Driver picks up -> Driver adds expenses -> Security check-in."""
        # 1. Admin creates pickup assignment for new car
        self.client.force_authenticate(user=self.admin)
        pickup_payload = {
            "assignmentType": "PICKUP",
            "carNumber": "MH04AB1234",
            "carMake": "Maruti",
            "carModel": "Swift",
            "customerName": "Rahul Sharma",
            "customerPhone": "9876543210",
            "customerAddress": "Thane West",
            "driverId": self.driver1.id,
            "pickupLocation": "Ghodbunder Road, Thane",
            "notes": "Call customer 15 mins before arrival",
        }
        create_res = self.client.post("/api/compat/driver-assignments/", pickup_payload, format="json")
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        assignment_id = create_res.data["id"]
        self.assertEqual(create_res.data["status"], "ASSIGNED")
        self.assertEqual(create_res.data["driverName"], "Ramesh Driver")

        # 2. Driver 1 lists assignments -> sees it
        self.client.force_authenticate(user=self.driver1)
        driver_list_res = self.client.get("/api/compat/driver-assignments/")
        self.assertEqual(driver_list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(driver_list_res.data["total"], 1)
        self.assertEqual(driver_list_res.data["documents"][0]["id"], assignment_id)

        # Driver 2 lists assignments -> sees nothing (data isolation)
        self.client.force_authenticate(user=self.driver2)
        driver2_res = self.client.get("/api/compat/driver-assignments/")
        self.assertEqual(driver2_res.data["total"], 0)

        # 3. Driver 1 marks vehicle picked up
        self.client.force_authenticate(user=self.driver1)
        update_res = self.client.patch(
            f"/api/compat/driver-assignments/{assignment_id}/",
            {"status": "PICKED_UP", "pickupLocation": "Ghodbunder Road, Thane"},
            format="json",
        )
        self.assertEqual(update_res.status_code, status.HTTP_200_OK)
        self.assertEqual(update_res.data["status"], "PICKED_UP")
        self.assertIsNotNone(update_res.data["startedAt"])

        # 4. Driver 1 adds multiple trip expenses
        exp1_res = self.client.post(
            f"/api/compat/driver-assignments/{assignment_id}/expenses/",
            {"category": "Fuel", "amount": 650.0, "description": "HP Petrol Pump Thane"},
            format="json",
        )
        self.assertEqual(exp1_res.status_code, status.HTTP_201_CREATED)

        exp2_res = self.client.post(
            f"/api/compat/driver-assignments/{assignment_id}/expenses/",
            {"category": "Toll", "amount": 85.0, "description": "Mulund Toll Naka"},
            format="json",
        )
        self.assertEqual(exp2_res.status_code, status.HTTP_201_CREATED)

        # Verify expense summary on assignment
        detail_res = self.client.get(f"/api/compat/driver-assignments/{assignment_id}/")
        self.assertEqual(len(detail_res.data["expenses"]), 2)
        self.assertEqual(detail_res.data["totalExpenses"], 735.0)

        # 5. Security checks vehicle in at workshop
        self.client.force_authenticate(user=self.security)
        # Create permanent Car first (standard Security flow)
        car = Car.objects.create(
            car_number="MH04AB1234",
            car_make="Maruti",
            car_model="Swift",
            customer_name="Rahul Sharma",
            customer_phone="9876543210",
        )
        # Check-in creates TempCar
        temp_car_payload = {
            "carsTableId": str(car.pk),
            "carStatus": 0,
            "purposeOfVisitAndAdvisors": ["1:advisor@t3.com"],
            "pickupAssignmentId": assignment_id,
        }
        temp_res = self.client.post("/api/compat/temp-cars/", temp_car_payload, format="json")
        self.assertEqual(temp_res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(temp_res.data["hasPickupAssignment"])
        self.assertEqual(temp_res.data["pickupAssignmentId"], assignment_id)

        # 6. Verify Pickup Assignment is linked and completed
        assignment = DriverAssignment.objects.get(pk=assignment_id)
        self.assertEqual(assignment.status, "COMPLETED")
        self.assertIsNotNone(assignment.completed_at)
        self.assertIsNotNone(assignment.temp_car)
        self.assertEqual(assignment.car, car)
        self.assertEqual(assignment.total_expenses, Decimal("735.00"))

        # 7. Verify driver cannot add more expenses once completed
        self.client.force_authenticate(user=self.driver1)
        bad_exp_res = self.client.post(
            f"/api/compat/driver-assignments/{assignment_id}/expenses/",
            {"category": "Parking", "amount": 50.0},
            format="json",
        )
        self.assertEqual(bad_exp_res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_03_drop_workflow(self):
        """Full drop flow: Workshop finishes -> Admin creates Drop -> Driver starts drop -> Driver adds expense -> Driver marks dropped."""
        # Create Car and completed JobCard
        car = Car.objects.create(
            car_number="MH02CD5678",
            car_make="Honda",
            car_model="City",
            customer_name="Pooja Patel",
            customer_phone="9988776655",
            customer_address="Bandra West, Mumbai",
        )
        jobcard = JobCard.objects.create(
            car_id=car.car_number,
            car_number=car.car_number,
            customer_name=car.customer_name,
            customer_phone=car.customer_phone,
            customer_address=car.customer_address,
            job_card_status=5,
            job_card_number=501,
            workflow_status=JobCard.WorkflowStatus.POST_DELIVERY_COMPLETED,
        )

        # 1. Admin creates Drop Assignment
        self.client.force_authenticate(user=self.admin)
        drop_payload = {
            "assignmentType": "DROP",
            "jobCardId": str(jobcard.id),
            "driverId": self.driver2.id,
            "dropLocation": "Hill Road, Bandra West",
            "notes": "Customer requested delivery before 5 PM",
        }
        create_res = self.client.post("/api/compat/driver-assignments/", drop_payload, format="json")
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        assignment_id = create_res.data["id"]
        self.assertEqual(create_res.data["assignmentType"], "DROP")
        self.assertEqual(create_res.data["status"], "ASSIGNED")
        self.assertEqual(create_res.data["carNumber"], "MH02CD5678")

        # 2. Driver 2 sees it on dashboard
        self.client.force_authenticate(user=self.driver2)
        list_res = self.client.get("/api/compat/driver-assignments/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(list_res.data["total"], 1)

        # 3. Driver 2 starts drop
        start_res = self.client.patch(
            f"/api/compat/driver-assignments/{assignment_id}/",
            {"status": "DROP_STARTED"},
            format="json",
        )
        self.assertEqual(start_res.status_code, status.HTTP_200_OK)
        self.assertEqual(start_res.data["status"], "DROP_STARTED")
        self.assertIsNotNone(start_res.data["startedAt"])

        # 4. Driver 2 records toll expense
        exp_res = self.client.post(
            f"/api/compat/driver-assignments/{assignment_id}/expenses/",
            {"category": "Toll", "amount": 100.0, "description": "Sea Link Toll"},
            format="json",
        )
        self.assertEqual(exp_res.status_code, status.HTTP_201_CREATED)

        # 5. Driver 2 marks vehicle as Dropped
        drop_res = self.client.patch(
            f"/api/compat/driver-assignments/{assignment_id}/",
            {"status": "DROPPED", "dropLocation": "Hill Road, Bandra West"},
            format="json",
        )
        self.assertEqual(drop_res.status_code, status.HTTP_200_OK)
        self.assertEqual(drop_res.data["status"], "DROPPED")
        self.assertIsNotNone(drop_res.data["completedAt"])

        # 6. Verify assignment finalized and expense history preserved
        assignment = DriverAssignment.objects.get(pk=assignment_id)
        self.assertEqual(assignment.status, "DROPPED")
        self.assertEqual(assignment.total_expenses, Decimal("100.00"))
        self.assertEqual(assignment.job_card, jobcard)

    def test_04_normal_vehicle_checkin_unaffected(self):
        """Verify normal vehicle check-in (without any driver pickup) continues working as before."""
        self.client.force_authenticate(user=self.security)
        car = Car.objects.create(
            car_number="MH01XY9999",
            car_make="Tata",
            car_model="Nexon",
            customer_name="Direct Customer",
            customer_phone="9123456789",
        )
        temp_payload = {
            "carsTableId": str(car.pk),
            "carStatus": 0,
            "purposeOfVisitAndAdvisors": ["1:advisor@t3.com"],
        }
        res = self.client.post("/api/compat/temp-cars/", temp_payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["carNumber"], "MH01XY9999")
        self.assertFalse(res.data.get("hasPickupAssignment", False))
