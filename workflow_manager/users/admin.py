from django.contrib import admin
from .models import CustomUser, Label, Role

admin.site.register(CustomUser)
admin.site.register(Label)
admin.site.register(Role)