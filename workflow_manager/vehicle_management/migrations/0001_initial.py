import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Car",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("car_number", models.CharField(max_length=100, unique=True)),
                ("car_make", models.CharField(blank=True, max_length=100)),
                ("car_model", models.CharField(blank=True, max_length=100)),
                ("location", models.CharField(blank=True, max_length=200)),
                ("purpose_of_visit", models.CharField(blank=True, max_length=200)),
                ("all_job_cards", models.JSONField(blank=True, default=list)),
                (
                    "cars_table_id",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                ("customer_name", models.CharField(blank=True, max_length=200)),
                ("customer_phone", models.CharField(blank=True, max_length=20)),
                ("customer_address", models.CharField(blank=True, max_length=300)),
                (
                    "purpose_of_visit_and_advisors",
                    models.JSONField(blank=True, default=list),
                ),
                ("customer_email", models.EmailField(blank=True, max_length=254)),
                (
                    "calling_status",
                    models.IntegerField(
                        default=0,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TempCar",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("job_card_id", models.CharField(blank=True, max_length=100)),
                (
                    "car_status",
                    models.IntegerField(
                        default=0,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                ("cars_table_id", models.CharField(blank=True, max_length=100)),
                (
                    "purpose_of_visit_and_advisors",
                    models.JSONField(blank=True, default=list),
                ),
                ("all_job_card_ids", models.JSONField(blank=True, default=list)),
                (
                    "car",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="temp_versions",
                        to="vehicle_management.car",
                    ),
                ),
            ],
        ),
    ]
