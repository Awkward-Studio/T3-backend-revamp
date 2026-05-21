from django.contrib import admin
from .models import InventoryMovement, Product

# Register your models here.
admin.site.register(Product)
admin.site.register(InventoryMovement)
