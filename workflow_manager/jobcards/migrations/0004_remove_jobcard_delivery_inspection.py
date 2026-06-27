from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("jobcards", "0003_workshop_features"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="jobcard",
            name="delivery_inspection",
        ),
    ]
