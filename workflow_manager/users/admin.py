from django.contrib import admin
from .models import CustomUser, Label

admin.site.register(CustomUser)
admin.site.register(Label)
