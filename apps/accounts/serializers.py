from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common import errors

from .models import Role
from .services import get_user_by_email


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    role = serializers.ChoiceField(choices=Role.choices)

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "OTP must be 6 digits."})


class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class LoginSerializer(serializers.Serializer):
    """Email + password -> JWT pair. The default TokenObtainPairSerializer wants a
    username, which this API deliberately does not expose, so login is custom."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = get_user_by_email(attrs["email"])
        if user is None or not user.check_password(attrs["password"]) or not user.is_active:
            raise errors.InvalidCredentials()
        profile = getattr(user, "profile", None)
        if profile is None or not profile.is_verified:
            raise errors.EmailNotVerified()

        refresh = RefreshToken.for_user(user)
        refresh["role"] = profile.role  # convenience claim; permissions still re-check the DB

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        return {"access": str(refresh.access_token), "refresh": str(refresh)}


class MeSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="profile.role")
    email_verified = serializers.BooleanField(source="profile.is_verified")

    class Meta:
        model = User
        fields = ["id", "email", "role", "email_verified", "date_joined"]
