from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobcards", "0004_remove_jobcard_delivery_inspection"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobcard",
            name="suggested_parts",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
