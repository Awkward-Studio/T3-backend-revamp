from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from jobcards.models import JobCard
from rest_framework import status
from rest_framework.test import APIClient
from users.models import Role, RoleName
from vehicle_management.models import Car, TempCar

from .models import CustomerWallet, Invoice, WalletTransaction


class CustomerWalletAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()

        self.biller_role, _ = Role.objects.get_or_create(name=RoleName.BILLER)
        self.security_role, _ = Role.objects.get_or_create(name=RoleName.SECURITY)

        self.biller_user = self.user_model.objects.create_user(
            username="biller",
            email="biller@example.com",
            password="password123",
            first_name="Bill",
            last_name="Er",
        )
        self.biller_user.roles.add(self.biller_role)

        self.security_user = self.user_model.objects.create_user(
            username="security",
            email="security@example.com",
            password="password123",
        )
        self.security_user.roles.add(self.security_role)

    def create_jobcard_for_car(self, car: Car, *, car_id: str = "JC-001") -> JobCard:
        temp_car = TempCar.objects.create(
            car=car,
            job_card_id=car_id,
            car_status=0,
            cars_table_id=str(car.id),
        )
        return JobCard.objects.create(
            car_id=car_id,
            temp_car=temp_car,
            car_number=car.car_number,
            job_card_status=0,
            customer_name=car.customer_name,
            customer_phone=car.customer_phone or "9999999999",
            purpose_of_visit="General Service",
        )

    def test_creating_permanent_car_auto_creates_wallet(self):
        car = Car.objects.create(
            car_number="MH01AB1234",
            customer_name="Amaan Khan",
            car_model="Toyota Fortuner",
        )

        wallet = CustomerWallet.objects.get(car=car)

        self.assertEqual(wallet.balance, Decimal("0.00"))
        self.assertEqual(CustomerWallet.objects.filter(car=car).count(), 1)

    def test_only_biller_can_access_wallet_list(self):
        Car.objects.create(
            car_number="MH02CD4321",
            customer_name="Zoya Shaikh",
            car_model="Honda City",
        )

        self.client.force_authenticate(user=self.security_user)
        forbidden_response = self.client.get("/api/wallets/")
        self.assertEqual(forbidden_response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.biller_user)
        allowed_response = self.client.get("/api/wallets/")
        self.assertEqual(allowed_response.status_code, status.HTTP_200_OK)
        self.assertEqual(allowed_response.data["count"], 1)
        self.assertEqual(len(allowed_response.data["results"]), 1)

    def test_add_credit_updates_wallet_and_creates_transaction(self):
        car = Car.objects.create(
            car_number="MH03EF6789",
            customer_name="Sara Ali",
            car_model="Hyundai Creta",
        )
        wallet = CustomerWallet.objects.get(car=car)

        self.client.force_authenticate(user=self.biller_user)
        response = self.client.post(
            f"/api/wallets/{car.id}/credits/",
            {"amount": "1500.00", "reason": "Overpayment"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("1500.00"))

        transaction_row = WalletTransaction.objects.get(wallet=wallet)
        self.assertEqual(
            transaction_row.type,
            WalletTransaction.TransactionType.CREDIT,
        )
        self.assertEqual(transaction_row.amount, Decimal("1500.00"))
        self.assertEqual(transaction_row.reason, "Overpayment")
        self.assertEqual(transaction_row.created_by, "Bill Er")

    def test_wallet_detail_returns_transaction_history(self):
        car = Car.objects.create(
            car_number="MH04GH2468",
            customer_name="Nadia Sheikh",
            car_model="Kia Seltos",
        )
        wallet = CustomerWallet.objects.get(car=car)
        WalletTransaction.objects.create(
            wallet=wallet,
            amount=Decimal("250.00"),
            reason="Goodwill Credit",
            type=WalletTransaction.TransactionType.CREDIT,
            created_by="Bill Er",
        )
        wallet.balance = Decimal("250.00")
        wallet.save(update_fields=["balance", "updated_at"])

        self.client.force_authenticate(user=self.biller_user)
        response = self.client.get(f"/api/wallets/{car.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["wallet"]["car_id"], car.id)
        self.assertEqual(response.data["current_balance"], "250.00")
        self.assertEqual(response.data["transactions"]["count"], 1)
        self.assertEqual(
            response.data["transactions"]["results"][0]["reason"],
            "Goodwill Credit",
        )

    def test_tax_invoice_settles_wallet_credit_only_on_completion(self):
        car = Car.objects.create(
            car_number="MH05IJ1357",
            customer_name="Areeba Khan",
            customer_phone="9898989898",
            car_model="Baleno",
        )
        wallet = CustomerWallet.objects.get(car=car)
        wallet.balance = Decimal("500.00")
        wallet.save(update_fields=["balance", "updated_at"])
        jobcard = self.create_jobcard_for_car(car, car_id="JC-005")

        self.client.force_authenticate(user=self.biller_user)

        quote_response = self.client.post(
            "/api/compat/invoices/",
            {
                "jobCardId": str(jobcard.pk),
                "invoiceSeries": "bds",
                "invoiceType": "Quote",
                "invoiceNumber": 1001,
                "invoiceCode": "BDS/1001",
                "invoiceUrl": "https://example.com/quote.pdf",
                "invoiceTotal": "400.00",
                "walletCreditUsed": "100.00",
                "finalAmount": "300.00",
            },
            format="json",
        )

        self.assertEqual(quote_response.status_code, status.HTTP_201_CREATED)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("500.00"))
        self.assertFalse(
            WalletTransaction.objects.filter(
                wallet=wallet, type=WalletTransaction.TransactionType.DEBIT
            ).exists()
        )

        tax_response = self.client.post(
            "/api/compat/invoices/",
            {
                "jobCardId": str(jobcard.pk),
                "invoiceSeries": "bds",
                "invoiceType": "Tax Invoice",
                "invoiceNumber": 1001,
                "invoiceCode": "BDS/1001",
                "invoiceUrl": "https://example.com/tax.pdf",
                "invoiceTotal": "400.00",
                "walletCreditUsed": "100.00",
                "finalAmount": "300.00",
            },
            format="json",
        )

        self.assertEqual(tax_response.status_code, status.HTTP_200_OK)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("400.00"))

        invoice = Invoice.objects.get(job_card=jobcard)
        self.assertEqual(invoice.wallet_credit_used, Decimal("100.00"))
        self.assertEqual(invoice.final_amount, Decimal("300.00"))
        self.assertIsNotNone(invoice.wallet_transaction_id)

        debit_transaction = WalletTransaction.objects.get(
            pk=invoice.wallet_transaction_id
        )
        self.assertEqual(
            debit_transaction.type, WalletTransaction.TransactionType.DEBIT
        )
        self.assertEqual(debit_transaction.amount, Decimal("100.00"))

    def test_non_biller_cannot_use_wallet_credits_on_invoice(self):
        car = Car.objects.create(
            car_number="MH06KL9753",
            customer_name="Hamza Noor",
            customer_phone="9797979797",
            car_model="Swift",
        )
        jobcard = self.create_jobcard_for_car(car, car_id="JC-006")

        self.client.force_authenticate(user=self.security_user)
        response = self.client.post(
            "/api/compat/invoices/",
            {
                "jobCardId": str(jobcard.pk),
                "invoiceSeries": "bds",
                "invoiceType": "Tax Invoice",
                "invoiceNumber": 1002,
                "invoiceCode": "BDS/1002",
                "invoiceUrl": "https://example.com/tax.pdf",
                "invoiceTotal": "400.00",
                "walletCreditUsed": "50.00",
                "finalAmount": "350.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Only billers", response.data["error"])

    def test_customer_portal_exposes_wallet_balance_and_history(self):
        car = Car.objects.create(
            car_number="MH07MN8642",
            customer_name="Sana Rizvi",
            customer_phone="9696969696",
            car_model="Ertiga",
        )
        wallet = CustomerWallet.objects.get(car=car)
        WalletTransaction.objects.create(
            wallet=wallet,
            amount=Decimal("250.00"),
            reason="Overpayment",
            type=WalletTransaction.TransactionType.CREDIT,
            created_by="Bill Er",
        )
        wallet.balance = Decimal("250.00")
        wallet.save(update_fields=["balance", "updated_at"])

        access_response = self.client.post(
            "/api/compat/portal/",
            {"licensePlate": car.car_number},
            format="json",
        )
        self.assertEqual(access_response.status_code, status.HTTP_200_OK)
        self.assertTrue(access_response.data["walletBalance"]["enabled"])
        self.assertEqual(access_response.data["walletBalance"]["amount"], 250.0)
        self.assertEqual(len(access_response.data["walletBalance"]["transactions"]), 1)
        self.assertEqual(
            access_response.data["walletBalance"]["transactions"][0]["reason"],
            "Overpayment",
        )
