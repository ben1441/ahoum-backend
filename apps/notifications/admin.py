from django.contrib import admin

from .models import EmailLog


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ["enrollment", "kind", "sent_at", "created_at"]
    list_filter = ["kind"]
