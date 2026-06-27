from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0005_invoice_final_amount_invoice_invoice_total_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="apply_gst",
            field=models.BooleanField(default=True),
        ),
    ]
