from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("jobcards", "0003_telecrmleadsync")]

    operations = [
        migrations.AlterField(
            model_name="telecrmleadsync",
            name="phone",
            field=models.CharField(max_length=32),
        ),
        migrations.AddField(
            model_name="telecrmleadsync",
            name="car_number",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="telecrmleadsync",
            name="period_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="telecrmleadsync",
            constraint=models.UniqueConstraint(
                fields=("phone", "car_number", "period_date"),
                name="unique_telecrm_lead_period",
            ),
        ),
    ]
