from django.contrib import admin

from .models import EmailOTP, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "role", "email_verified_at"]
    list_filter = ["role"]
    search_fields = ["user__email"]


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ["user", "purpose", "expires_at", "attempts", "invalidated_at"]
    readonly_fields = ["code_hash"]
