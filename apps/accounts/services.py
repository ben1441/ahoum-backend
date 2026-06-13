"""Account business logic. Views stay thin; rules live here and raise DomainErrors."""

import secrets
import uuid

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.utils import timezone

from apps.common import errors
from apps.notifications.tasks import send_otp_email_task

from .models import EmailOTP, Profile


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(email: str) -> User | None:
    return User.objects.filter(email__iexact=normalize_email(email)).first()


@transaction.atomic
def signup(*, email: str, password: str, role: str) -> User | None:
    """Create an unverified user and send an OTP.

    If the email is already registered this is a silent no-op (anti-enumeration:
    the API responds identically either way), except that an unverified existing
    user gets a fresh OTP so they can complete signup.
    """
    email = normalize_email(email)
    existing = get_user_by_email(email)
    if existing is not None:
        profile = getattr(existing, "profile", None)
        if profile is not None and not profile.is_verified:
            try:
                issue_otp(existing)
            except errors.OTPCooldown:
                pass  # keep the response generic; a recent code is already in their inbox
        return None

    # The spec mandates the default User model, which requires a username.
    # Signup must not accept one, so generate an opaque, collision-free value.
    user = User.objects.create_user(
        username=uuid.uuid4().hex[:30],
        email=email,
        password=password,
    )
    Profile.objects.create(user=user, role=role)
    user.groups.add(Group.objects.get(name=role))
    issue_otp(user)
    return user


def issue_otp(user: User) -> EmailOTP:
    """Create a fresh OTP (invalidating previous ones) and queue the email."""
    now = timezone.now()
    latest = user.otps.filter(purpose=EmailOTP.Purpose.SIGNUP).order_by("-created_at").first()
    if latest is not None:
        cooldown = settings.OTP_RESEND_COOLDOWN_SECONDS
        if (now - latest.created_at).total_seconds() < cooldown:
            raise errors.OTPCooldown()

    user.otps.filter(invalidated_at__isnull=True).update(invalidated_at=now)

    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = EmailOTP.objects.create(
        user=user,
        code_hash=make_password(code),
        expires_at=now + timezone.timedelta(seconds=settings.OTP_TTL_SECONDS),
    )
    transaction.on_commit(lambda: send_otp_email_task.delay(user.id, code))
    return otp


def verify_email(*, email: str, otp: str) -> User:
    user = get_user_by_email(email)
    if user is None or not hasattr(user, "profile"):
        # Same error as a wrong code: never reveal whether an email is registered.
        raise errors.OTPInvalid()

    if user.profile.is_verified:
        return user  # idempotent: verifying twice is not an error

    # The whole check runs under a row lock so concurrent attempts can't race the
    # counter. A wrong code must *persist* the attempt increment even though we then
    # signal failure, so we commit the atomic block and raise outside it — raising
    # inside would roll the increment back.
    matched = False
    with transaction.atomic():
        candidate = (
            user.otps.select_for_update()
            .filter(purpose=EmailOTP.Purpose.SIGNUP, invalidated_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if candidate is None:
            raise errors.OTPInvalid()
        if candidate.is_expired:
            raise errors.OTPExpired()
        if candidate.attempts >= settings.OTP_MAX_ATTEMPTS:
            raise errors.OTPMaxAttempts()

        matched = check_password(otp, candidate.code_hash)
        if matched:
            candidate.invalidated_at = timezone.now()
            candidate.save(update_fields=["invalidated_at", "updated_at"])
            user.profile.email_verified_at = timezone.now()
            user.profile.save(update_fields=["email_verified_at", "updated_at"])
        else:
            candidate.attempts += 1
            candidate.save(update_fields=["attempts", "updated_at"])

    if not matched:
        if candidate.attempts >= settings.OTP_MAX_ATTEMPTS:
            raise errors.OTPMaxAttempts()
        raise errors.OTPInvalid()
    return user


def resend_otp(*, email: str) -> None:
    """Re-send a code. Silent no-op for unknown/verified emails or when within the
    resend cooldown — the endpoint always returns the same generic response so it
    can't be used to probe which emails are registered."""
    user = get_user_by_email(email)
    if user is None or not hasattr(user, "profile") or user.profile.is_verified:
        return
    try:
        issue_otp(user)
    except errors.OTPCooldown:
        pass
