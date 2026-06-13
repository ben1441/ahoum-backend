from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "location", "language", "starts_at", "capacity", "created_by"]
    list_filter = ["language", "location"]
    search_fields = ["title", "description"]
