from django.db import migrations


def backfill_customer_portals(apps, schema_editor):
    Car = apps.get_model("vehicle_management", "Car")
    CustomerPortal = apps.get_model("vehicle_management", "CustomerPortal")

    existing_car_ids = set(CustomerPortal.objects.values_list("car_id", flat=True))
    portals_to_create = [
        CustomerPortal(car_id=car.id)
        for car in Car.objects.all().iterator()
        if car.id not in existing_car_ids
    ]
    if portals_to_create:
        CustomerPortal.objects.bulk_create(portals_to_create, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("vehicle_management", "0005_customerportal"),
    ]

    operations = [
        migrations.RunPython(backfill_customer_portals, migrations.RunPython.noop),
    ]
