from django.contrib import admin

from vehicle_management.models import (
    Car,
    CustomerPortal,
    DriverAssignment,
    DriverExpense,
    TempCar,
)

admin.site.register(Car)
admin.site.register(CustomerPortal)
admin.site.register(TempCar)
admin.site.register(DriverAssignment)
admin.site.register(DriverExpense)
