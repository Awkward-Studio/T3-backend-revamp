from django.contrib import admin
from .models import CustomUser, Label, Role
from django.contrib.auth.admin import UserAdmin



class CustomUserAdmin(UserAdmin):
    model = CustomUser

    fieldsets = UserAdmin.fieldsets + (
        ("Custom Fields", {
            "fields": ("roles", "labels"),
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Custom Fields", {
            "fields": ("roles", "labels"),
        }),
    )

admin.site.register(CustomUser, CustomUserAdmin)

# admin.site.register(CustomUser)
admin.site.register(Label)
admin.site.register(Role)