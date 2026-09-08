from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("jobcards", "0002_deletedjobcard_alter_jobcard_car_id")]

    operations = [
        migrations.CreateModel(
            name="TelecrmLeadSync",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(max_length=32, unique=True)),
                ("payload_hash", models.CharField(blank=True, max_length=64)),
                ("last_payload", models.JSONField(blank=True, default=dict)),
                ("last_queued_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        )
    ]
