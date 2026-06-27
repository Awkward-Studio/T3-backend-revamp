from decimal import Decimal

from django.db import migrations

DEFAULT_WALLET_BALANCE = Decimal("0.00")


def create_missing_wallets(apps, schema_editor):
    Car = apps.get_model("vehicle_management", "Car")
    CustomerWallet = apps.get_model("billing", "CustomerWallet")

    existing_car_ids = set(CustomerWallet.objects.values_list("car_id", flat=True))

    wallets_to_create = [
        CustomerWallet(car_id=car.id, balance=DEFAULT_WALLET_BALANCE)
        for car in Car.objects.exclude(id__in=existing_car_ids).iterator()
    ]

    if wallets_to_create:
        CustomerWallet.objects.bulk_create(wallets_to_create, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0003_customerwallet_wallettransaction"),
    ]

    operations = [
        migrations.RunPython(create_missing_wallets, migrations.RunPython.noop),
    ]
