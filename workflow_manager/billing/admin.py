from django.contrib import admin

from billing.models import CustomerWallet, Invoice, InvoiceCounter, WalletTransaction

admin.site.register(Invoice)
admin.site.register(InvoiceCounter)
admin.site.register(CustomerWallet)
admin.site.register(WalletTransaction)
