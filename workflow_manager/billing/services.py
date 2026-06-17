from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from vehicle_management.models import Car

from .models import CustomerWallet, Invoice, WalletTransaction

DEFAULT_WALLET_BALANCE = Decimal("0.00")
ZERO_AMOUNT = Decimal("0.00")
MONEY_QUANTIZER = Decimal("0.01")


def quantize_money(value) -> Decimal:
    return Decimal(str(value or ZERO_AMOUNT)).quantize(
        MONEY_QUANTIZER, rounding=ROUND_HALF_UP
    )


def get_actor_display_name(user) -> str:
    if not getattr(user, "is_authenticated", False):
        return ""

    full_name = f"{user.first_name} {user.last_name}".strip()
    return full_name or user.email or user.username or str(user.pk)


def ensure_wallet_for_car(car):
    wallet, _ = CustomerWallet.objects.get_or_create(
        car=car,
        defaults={"balance": DEFAULT_WALLET_BALANCE},
    )
    return wallet


def get_wallet_for_jobcard(jobcard):
    temp_car = getattr(jobcard, "temp_car", None)
    if temp_car and getattr(temp_car, "car_id", None):
        return ensure_wallet_for_car(temp_car.car)

    car_number = str(getattr(jobcard, "car_number", "") or "").strip()
    if not car_number:
        return None

    car = Car.objects.filter(car_number__iexact=car_number).first()
    if not car:
        return None

    return ensure_wallet_for_car(car)


@transaction.atomic
def add_wallet_credit(
    *, wallet: CustomerWallet, amount, reason: str, created_by: str = ""
):
    amount = quantize_money(amount)
    if amount <= 0:
        raise ValueError("Amount must be greater than 0.")

    if not str(reason or "").strip():
        raise ValueError("Reason is required.")

    locked_wallet = CustomerWallet.objects.select_for_update().get(pk=wallet.pk)
    locked_wallet.balance = quantize_money(
        (locked_wallet.balance or ZERO_AMOUNT) + amount
    )
    locked_wallet.save(update_fields=["balance", "updated_at"])

    transaction_row = WalletTransaction.objects.create(
        wallet=locked_wallet,
        amount=amount,
        reason=str(reason).strip(),
        type=WalletTransaction.TransactionType.CREDIT,
        created_by=str(created_by or "").strip(),
    )

    return locked_wallet, transaction_row


@transaction.atomic
def apply_wallet_credit_to_invoice(
    *,
    invoice: Invoice,
    amount,
    invoice_total,
    created_by: str = "",
    reason: str = "",
):
    amount = quantize_money(amount)
    invoice_total = quantize_money(invoice_total)

    if amount <= 0:
        raise ValueError("Credit amount must be greater than 0.")
    if invoice_total <= 0:
        raise ValueError("Invoice total must be greater than 0.")
    if amount > invoice_total:
        raise ValueError("Credit amount cannot exceed invoice total.")

    locked_invoice = (
        Invoice.objects.select_for_update()
        .select_related("job_card", "wallet_transaction")
        .get(pk=invoice.pk)
    )

    existing_credit = quantize_money(locked_invoice.wallet_credit_used)
    if locked_invoice.wallet_transaction_id:
        if existing_credit != amount:
            raise ValueError(
                "Wallet credits have already been settled for this invoice."
            )
        return locked_invoice, locked_invoice.wallet_transaction

    wallet = get_wallet_for_jobcard(locked_invoice.job_card)
    if not wallet:
        raise ValueError(
            "Wallet credits are available only for permanent cars with a customer wallet."
        )

    locked_wallet = CustomerWallet.objects.select_for_update().get(pk=wallet.pk)
    current_balance = quantize_money(locked_wallet.balance)
    if amount > current_balance:
        raise ValueError("Credit amount cannot exceed wallet balance.")

    debit_reason = str(reason or "").strip()
    if not debit_reason:
        invoice_label = (
            locked_invoice.invoice_code
            or f"#{locked_invoice.invoice_number}"
            or str(locked_invoice.pk)
        )
        debit_reason = f"Used on {locked_invoice.invoice_type} {invoice_label}"

    locked_wallet.balance = quantize_money(current_balance - amount)
    locked_wallet.save(update_fields=["balance", "updated_at"])

    transaction_row = WalletTransaction.objects.create(
        wallet=locked_wallet,
        amount=amount,
        reason=debit_reason,
        type=WalletTransaction.TransactionType.DEBIT,
        created_by=str(created_by or "").strip(),
    )

    locked_invoice.wallet_credit_used = amount
    locked_invoice.wallet_transaction = transaction_row
    locked_invoice.final_amount = quantize_money(invoice_total - amount)
    locked_invoice.save(
        update_fields=[
            "wallet_credit_used",
            "wallet_transaction",
            "final_amount",
            "updated_at",
        ]
    )

    return locked_invoice, transaction_row
