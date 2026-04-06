from django.contrib import admin
from catalog.models.insurers_model import InsuranceProvider
from catalog.models.vehicle_models_model import VehilceModel
from catalog.models.labour_models import Labour

admin.site.register(InsuranceProvider)
admin.site.register(VehilceModel)
admin.site.register(Labour)
