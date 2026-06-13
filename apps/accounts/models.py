from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


class Role(models.TextChoices):
    SEEKER = "seeker", "Seeker"
    FACILITATOR = "facilitator", "Facilitator"


class Profile(TimeStampedModel):
    """Role and verification state for the default Django User (which must not be swapped)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.email} ({self.role})"

    @property
    def is_verified(self) -> bool:
        return self.email_verified_at is not None


class EmailOTP(TimeStampedModel):
    """One-time verification code. Only a salted hash is stored, never the code itself."""

    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Signup"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otps"
    )
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.SIGNUP)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    invalidated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose", "created_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.user.email} (expires {self.expires_at:%H:%M:%S})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_active(self) -> bool:
        return self.invalidated_at is None and not self.is_expired
