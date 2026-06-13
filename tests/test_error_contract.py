"""Every error response must carry the {"detail", "code"} contract."""

import pytest
from django.urls import reverse

from apps.common.errors import ErrorCode

pytestmark = pytest.mark.django_db


def test_validation_error_shape(api):
    resp = api.post(reverse("signup"), {"email": "not-an-email", "role": "seeker"})
    assert resp.status_code == 400
    assert set(resp.data) >= {"detail", "code", "errors"}
    assert resp.data["code"] == ErrorCode.VALIDATION_ERROR
    assert "email" in resp.data["errors"]


def test_not_authenticated_shape(api):
    resp = api.get(reverse("event-list"))
    assert resp.status_code == 401
    assert resp.data["code"] == ErrorCode.NOT_AUTHENTICATED
    assert set(resp.data) == {"detail", "code"}


def test_permission_denied_shape(seeker_client):
    resp = seeker_client.post(reverse("event-list"), {})
    assert resp.status_code == 403
    assert resp.data["code"] == ErrorCode.PERMISSION_DENIED


def test_not_found_shape(seeker_client):
    resp = seeker_client.get(reverse("event-detail", args=[999999]))
    assert resp.status_code == 404
    assert resp.data["code"] == ErrorCode.NOT_FOUND


def test_method_not_allowed_shape(seeker_client):
    # enrollment list is GET-only
    resp = seeker_client.delete(reverse("enrollment-list"))
    assert resp.status_code == 405
    assert resp.data["code"] == ErrorCode.METHOD_NOT_ALLOWED


def test_invalid_token_shape(api):
    api.credentials(HTTP_AUTHORIZATION="Bearer not.a.real.token")
    resp = api.get(reverse("event-list"))
    assert resp.status_code == 401
    assert "code" in resp.data
