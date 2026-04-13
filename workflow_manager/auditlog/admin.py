from django.contrib import admin

from .models import HistoryEntry


@admin.register(HistoryEntry)
class HistoryEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "object_type", "object_id", "operation_type", "user_email")
    list_filter = ("object_type", "operation_type", "created_at")
    search_fields = ("object_id", "user_email", "user_name")
