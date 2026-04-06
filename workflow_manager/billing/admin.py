from django.contrib import admin
from billing.models import Invoice, InvoiceCounter

admin.site.register(Invoice)
admin.site.register(InvoiceCounter)
