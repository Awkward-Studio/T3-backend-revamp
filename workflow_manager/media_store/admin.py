from django.contrib import admin

from .models import UploadedAsset


@admin.register(UploadedAsset)
class UploadedAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "original_name", "content_type", "created_at")
    list_filter = ("kind", "created_at")
