"""Auth + OTP flow: signup -> verify -> login -> refresh, plus the security edges."""

import pytest
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import EmailOTP, Profile, Role
from apps.common.errors import ErrorCode

pytestmark = pytest.mark.django_db


def test_signup_creates_unverified_user_and_sends_otp(signup_user):
    resp, _ = signup_user(email="Alice@Example.com")
    assert resp.status_code == 201
    user = User.objects.get(email__iexact="alice@example.com")
    assert user.email == "alice@example.com"  # normalized to lowercase
    assert user.username != "alice@example.com"  # username is opaque, not the email
    assert user.profile.role == Role.SEEKER
    assert not user.profile.is_verified
    assert user.groups.filter(name="seeker").exists()
    assert len(mail.outbox) == 1


def test_signup_rejects_weak_password(api):
    resp = api.post(reverse("signup"), {"email": "a@b.com", "password": "123", "role": "seeker"})
    assert resp.status_code == 400
    assert resp.data["code"] == ErrorCode.VALIDATION_ERROR


def test_signup_duplicate_email_is_silent(signup_user):
    signup_user(email="dup@example.com")
    resp, _ = signup_user(email="dup@example.com")
    # Anti-enumeration: identical 201 response, and no second account created.
    assert resp.status_code == 201
    assert User.objects.filter(email__iexact="dup@example.com").count() == 1


def test_verify_email_happy_path(api, signup_user):
    _, code = signup_user(email="bob@example.com", role="facilitator")
    resp = api.post(reverse("verify-email"), {"email": "bob@example.com", "otp": code})
    assert resp.status_code == 200
    assert User.objects.get(email="bob@example.com").profile.is_verified


def test_verify_email_wrong_code_increments_attempts(api, signup_user):
    signup_user(email="c@example.com")
    resp = api.post(reverse("verify-email"), {"email": "c@example.com", "otp": "000000"})
    assert resp.status_code == 400
    assert resp.data["code"] == ErrorCode.OTP_INVALID
    otp = EmailOTP.objects.get(user__email="c@example.com")
    assert otp.attempts == 1


def test_verify_email_max_attempts_locks_code(api, signup_user, settings):
    signup_user(email="d@example.com")
    # Use a guaranteed-wrong code so we always hit the attempt counter.
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        resp = api.post(reverse("verify-email"), {"email": "d@example.com", "otp": "000000"})
    assert resp.status_code == 429
    assert resp.data["code"] == ErrorCode.OTP_MAX_ATTEMPTS


def test_verify_email_expired_code(api, signup_user):
    _, code = signup_user(email="e@example.com")
    otp = EmailOTP.objects.get(user__email="e@example.com")
    otp.expires_at = timezone.now() - timezone.timedelta(seconds=1)
    otp.save(update_fields=["expires_at"])
    resp = api.post(reverse("verify-email"), {"email": "e@example.com", "otp": code})
    assert resp.status_code == 400
    assert resp.data["code"] == ErrorCode.OTP_EXPIRED


def test_resend_otp_cooldown_is_silent(api, signup_user, settings):
    settings.OTP_RESEND_COOLDOWN_SECONDS = 300
    signup_user(email="f@example.com")
    before = len(mail.outbox)
    # Immediate resend is within cooldown -> generic 200, no new email, no leak.
    resp = api.post(reverse("resend-otp"), {"email": "f@example.com"})
    assert resp.status_code == 200
    assert len(mail.outbox) == before


def test_resend_otp_unknown_email_is_silent(api):
    resp = api.post(reverse("resend-otp"), {"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert len(mail.outbox) == 0


def test_unverified_user_cannot_login(api, signup_user):
    signup_user(email="g@example.com")
    resp = api.post(reverse("login"), {"email": "g@example.com", "password": "sup3rsecret!"})
    assert resp.status_code == 403
    assert resp.data["code"] == ErrorCode.EMAIL_NOT_VERIFIED


def _make_verified_user(email):
    user = User.objects.create_user(username=email[:20], email=email)
    user.set_password("sup3rsecret!")
    user.save()
    Profile.objects.create(user=user, role=Role.SEEKER, email_verified_at=timezone.now())
    return user


def test_login_returns_token_pair_and_refresh_rotates(api):
    _make_verified_user("h@example.com")
    resp = api.post(reverse("login"), {"email": "h@example.com", "password": "sup3rsecret!"})
    assert resp.status_code == 200
    assert "access" in resp.data and "refresh" in resp.data

    rotated = api.post(reverse("refresh"), {"refresh": resp.data["refresh"]})
    assert rotated.status_code == 200
    assert "access" in rotated.data


def test_login_invalid_credentials(api):
    _make_verified_user("i@example.com")
    resp = api.post(reverse("login"), {"email": "i@example.com", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.data["code"] == ErrorCode.INVALID_CREDENTIALS


def test_otp_is_stored_hashed_not_plaintext(signup_user):
    _, code = signup_user(email="j@example.com")
    otp = EmailOTP.objects.get(user__email="j@example.com")
    assert otp.code_hash != code
    assert otp.code_hash != make_password(code)  # salted -> different each time


def test_me_endpoint_requires_auth_and_returns_role(api, seeker_client, seeker):
    resp = seeker_client.get(reverse("me"))
    assert resp.status_code == 200
    assert resp.data["role"] == Role.SEEKER
    assert resp.data["email"] == seeker.email

    anon = api.get(reverse("me"))
    assert anon.status_code == 401
    assert anon.data["code"] == ErrorCode.NOT_AUTHENTICATED
