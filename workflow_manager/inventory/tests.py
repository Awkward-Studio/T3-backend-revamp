from django.test import TestCase

from jobcards.models import CurrentPart, JobCard

from .models import Product
from .services import StockError, consume_jobcard_inventory


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
