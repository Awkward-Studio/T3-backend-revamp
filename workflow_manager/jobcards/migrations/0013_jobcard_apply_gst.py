from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jobcards", "0012_jobcard_required_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobcard",
            name="apply_gst",
            field=models.BooleanField(default=True),
        ),
    ]
