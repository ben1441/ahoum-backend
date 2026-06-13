import pytest
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from tests.factories import make_facilitator, make_seeker


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def signup_user(api, django_capture_on_commit_callbacks):
    """Run signup with on_commit callbacks executed (so the OTP email is sent under
    pytest-django's rollback transactions) and return (response, otp_code)."""

    def _signup(email="user@example.com", password="sup3rsecret!", role="seeker"):
        with django_capture_on_commit_callbacks(execute=True):
            resp = api.post(reverse("signup"), {"email": email, "password": password, "role": role})
        code = None
        if mail.outbox:
            code = "".join(c for c in mail.outbox[-1].body if c.isdigit())[:6]
        return resp, code

    return _signup


@pytest.fixture
def seeker(db):
    return make_seeker()


@pytest.fixture
def facilitator(db):
    return make_facilitator()


def _auth(client, user):
    """Authenticate a client as ``user`` by minting a JWT, exercising the real
    token path rather than force_authenticate."""
    from rest_framework_simplejwt.tokens import RefreshToken

    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def seeker_client(seeker):
    # Independent client so the bare `api` fixture stays anonymous.
    return _auth(APIClient(), seeker)


@pytest.fixture
def facilitator_client(facilitator):
    return _auth(APIClient(), facilitator)


@pytest.fixture
def as_user():
    """Factory fixture: return a client authenticated as the given user."""

    def _make(user):
        return _auth(APIClient(), user)

    return _make
