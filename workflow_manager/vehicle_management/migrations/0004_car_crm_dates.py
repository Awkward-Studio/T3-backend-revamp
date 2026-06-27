# Generated for customer CRM date attributes.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vehicle_management", "0003_car_timestamps"),
    ]

    operations = [
        migrations.AddField(
            model_name="car",
            name="anniversary_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="car",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="car",
            name="insurance_policy_expiry_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
