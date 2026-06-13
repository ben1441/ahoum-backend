from django.contrib import admin

from .models import Enrollment


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ["seeker", "event", "status", "created_at", "canceled_at"]
    list_filter = ["status"]
    search_fields = ["seeker__email", "event__title"]
