from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jobcards", "0013_jobcard_apply_gst"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobcard",
            name="company_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="jobcard",
            name="company_phone_number",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
    ]
