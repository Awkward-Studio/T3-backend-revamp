from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from jobcards.models import CurrentPart, JobCard

from .models import Product
from .services import StockError, consume_jobcard_inventory, invoice_consumes_inventory


class InventoryConsumptionTests(TestCase):
    def create_jobcard(self):
        return JobCard.objects.create(
            car_id="JC-1",
            car_number="KA01AB1234",
            job_card_status=1,
            customer_name="Test Customer",
            customer_phone="9999999999",
        )

    def create_product(self, name, quantity):
        return Product.objects.create(
            name=name,
            sku=name.upper(),
            quantity=quantity,
            price=100,
            mrp=100,
            gst=18,
            cgst=9,
            sgst=9,
        )

    def add_part(self, jobcard, product, quantity):
        return CurrentPart.objects.create(
            job_card=jobcard,
            product=product,
            part_id=str(product.id),
            part_name=product.name,
            part_number=product.sku,
            quantity=quantity,
            mrp=product.mrp,
            sub_total=100 * quantity,
            total_tax=18 * quantity,
            amount=118 * quantity,
            gst=18,
            cgst=9,
            sgst=9,
        )

    def test_consumes_inventory_once(self):
        jobcard = self.create_jobcard()
        product = self.create_product("filter", 5)
        self.add_part(jobcard, product, 2)

        movements = consume_jobcard_inventory(jobcard)
        product.refresh_from_db()
        jobcard.refresh_from_db()

        self.assertEqual(product.quantity, 3)
        self.assertEqual(len(movements), 1)
        self.assertIsNotNone(jobcard.inventory_consumed_at)
        self.assertEqual(jobcard.job_card_status, 5)

        second_movements = consume_jobcard_inventory(jobcard)
        product.refresh_from_db()

        self.assertEqual(product.quantity, 3)
        self.assertEqual(second_movements, [])

    def test_insufficient_stock_rolls_back_all_deductions(self):
        jobcard = self.create_jobcard()
        available = self.create_product("available", 5)
        low_stock = self.create_product("low", 1)
        self.add_part(jobcard, available, 2)
        self.add_part(jobcard, low_stock, 2)

        with self.assertRaises(StockError):
            consume_jobcard_inventory(jobcard)

        available.refresh_from_db()
        low_stock.refresh_from_db()
        jobcard.refresh_from_db()

        self.assertEqual(available.quantity, 5)
        self.assertEqual(low_stock.quantity, 1)
        self.assertIsNone(jobcard.inventory_consumed_at)

    def test_only_tax_invoice_consumes_inventory(self):
        self.assertFalse(invoice_consumes_inventory("Quote"))
        self.assertFalse(invoice_consumes_inventory("Pro-Forma Invoice"))
        self.assertFalse(invoice_consumes_inventory("Job Card"))
        self.assertTrue(invoice_consumes_inventory("Tax Invoice"))


class InventoryQuoteFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="admin@example.com",
            email="admin@example.com",
            password="testpass",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_quote_keeps_product_in_inventory_and_jobcard_parts(self):
        product_response = self.client.post(
            "/api/compat/parts/",
            {
                "partName": "Quote Only Part",
                "partNumber": "QOP-1",
                "hsn": "8708",
                "mrp": 100,
                "gst": 18,
                "cgst": 9,
                "sgst": 9,
                "quantity": 3,
            },
            format="json",
        )
        self.assertEqual(product_response.status_code, 201)
        product_id = product_response.data["$id"]

        jobcard = JobCard.objects.create(
            car_id="JC-QUOTE",
            car_number="KA01AB1234",
            job_card_status=2,
            customer_name="Test Customer",
            customer_phone="9999999999",
        )

        part_payload = {
            **product_response.data,
            "partId": product_id,
            "quantity": 1,
            "subTotal": 100,
            "totalTax": 18,
            "amount": 118,
        }
        patch_response = self.client.patch(
            f"/api/compat/jobcards/{jobcard.pk}/",
            {"parts": [part_payload], "jobCardStatus": 3},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)

        invoice_response = self.client.post(
            "/api/compat/invoices/",
            {
                "jobCardId": str(jobcard.pk),
                "invoiceSeries": "T3",
                "invoiceType": "Quote",
                "invoiceNumber": 1,
                "invoiceCode": "T3/1",
                "invoiceUrl": "https://example.com/quote.pdf",
                "carNumber": jobcard.car_number,
            },
            format="json",
        )
        self.assertIn(invoice_response.status_code, [200, 201])

        product = Product.objects.get(pk=product_id)
        self.assertEqual(product.quantity, 3)
        self.assertTrue(CurrentPart.objects.filter(job_card=jobcard, product=product).exists())

        list_response = self.client.get("/api/compat/parts/")
        self.assertEqual(list_response.status_code, 200)
        listed_ids = {item["$id"] for item in list_response.data["documents"]}
        self.assertIn(product_id, listed_ids)

        jobcard_response = self.client.get(f"/api/compat/jobcards/{jobcard.pk}/")
        self.assertEqual(jobcard_response.status_code, 200)
        self.assertEqual(jobcard_response.data["currentParts"][0]["partId"], product_id)

    def test_consumed_jobcard_rejects_commercial_edits_but_allows_status(self):
        product = Product.objects.create(
            name="Final Part",
            sku="FINAL-1",
            quantity=2,
            price=100,
            mrp=100,
            gst=18,
            cgst=9,
            sgst=9,
        )
        jobcard = JobCard.objects.create(
            car_id="JC-FINAL",
            car_number="KA01AB1234",
            job_card_status=4,
            customer_name="Test Customer",
            customer_phone="9999999999",
            workflow_status=JobCard.WorkflowStatus.POST_DELIVERY_COMPLETED,
        )
        CurrentPart.objects.create(
            job_card=jobcard,
            product=product,
            part_id=str(product.id),
            part_name=product.name,
            part_number=product.sku,
            quantity=1,
            mrp=product.mrp,
            sub_total=100,
            total_tax=18,
            amount=118,
            gst=18,
            cgst=9,
            sgst=9,
        )
        consume_jobcard_inventory(jobcard)

        blocked_response = self.client.patch(
            f"/api/compat/jobcards/{jobcard.pk}/",
            {"labour": []},
            format="json",
        )
        self.assertEqual(blocked_response.status_code, 400)

        status_response = self.client.patch(
            f"/api/compat/jobcards/{jobcard.pk}/",
            {"jobCardStatus": 6, "gatePassPDF": "https://example.com/gate-pass.pdf"},
            format="json",
        )
        self.assertEqual(status_response.status_code, 200)
