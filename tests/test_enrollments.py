"""Enrollment rules: capacity, re-enroll after cancel, double-enroll, listings."""

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.common.errors import ErrorCode
from apps.enrollments.models import Enrollment
from tests.factories import EventFactory, make_seeker

pytestmark = pytest.mark.django_db


def test_seeker_can_enroll(seeker_client, facilitator):
    event = EventFactory(created_by=facilitator, capacity=5)
    resp = seeker_client.post(reverse("event-enroll", args=[event.id]))
    assert resp.status_code == 201
    assert resp.data["status"] == "enrolled"
    assert Enrollment.objects.filter(event=event, status="enrolled").count() == 1


def test_double_enroll_returns_409(seeker_client, facilitator):
    event = EventFactory(created_by=facilitator, capacity=5)
    seeker_client.post(reverse("event-enroll", args=[event.id]))
    resp = seeker_client.post(reverse("event-enroll", args=[event.id]))
    assert resp.status_code == 409
    assert resp.data["code"] == ErrorCode.ALREADY_ENROLLED


def test_enroll_respects_capacity(seeker_client, seeker, facilitator):
    event = EventFactory(created_by=facilitator, capacity=1)
    # Fill the single seat with another seeker.
    Enrollment.objects.create(event=event, seeker=make_seeker())
    resp = seeker_client.post(reverse("event-enroll", args=[event.id]))
    assert resp.status_code == 409
    assert resp.data["code"] == ErrorCode.EVENT_FULL


def test_unlimited_capacity_never_full(seeker_client, facilitator):
    event = EventFactory(created_by=facilitator, capacity=None)
    for _ in range(5):
        Enrollment.objects.create(event=event, seeker=make_seeker())
    resp = seeker_client.post(reverse("event-enroll", args=[event.id]))
    assert resp.status_code == 201


def test_cannot_enroll_in_started_event(seeker_client, facilitator):
    now = timezone.now()
    event = EventFactory(
        created_by=facilitator,
        starts_at=now - timezone.timedelta(hours=1),
        ends_at=now + timezone.timedelta(hours=1),
    )
    resp = seeker_client.post(reverse("event-enroll", args=[event.id]))
    assert resp.status_code == 409
    assert resp.data["code"] == ErrorCode.EVENT_ALREADY_STARTED


def test_facilitator_cannot_enroll(facilitator_client, facilitator):
    event = EventFactory(created_by=facilitator, capacity=5)
    resp = facilitator_client.post(reverse("event-enroll", args=[event.id]))
    assert resp.status_code == 403


def test_cancel_then_reenroll(seeker_client, facilitator):
    event = EventFactory(created_by=facilitator, capacity=5)
    seeker_client.post(reverse("event-enroll", args=[event.id]))
    cancel = seeker_client.post(reverse("event-cancel", args=[event.id]))
    assert cancel.status_code == 200
    assert cancel.data["status"] == "canceled"

    # Re-enrolling after cancel is allowed (partial unique constraint permits it).
    again = seeker_client.post(reverse("event-enroll", args=[event.id]))
    assert again.status_code == 201
    assert Enrollment.objects.filter(event=event, status="enrolled").count() == 1
    assert Enrollment.objects.filter(event=event, status="canceled").count() == 1


def test_cancel_when_not_enrolled_returns_409(seeker_client, facilitator):
    event = EventFactory(created_by=facilitator, capacity=5)
    resp = seeker_client.post(reverse("event-cancel", args=[event.id]))
    assert resp.status_code == 409
    assert resp.data["code"] == ErrorCode.NOT_ENROLLED


def test_enroll_nonexistent_event_404(seeker_client):
    resp = seeker_client.post(reverse("event-enroll", args=[999999]))
    assert resp.status_code == 404


# --- Listings ---------------------------------------------------------------


def test_list_upcoming_and_past_enrollments(seeker_client, seeker, facilitator):
    now = timezone.now()
    upcoming = EventFactory(
        created_by=facilitator,
        starts_at=now + timezone.timedelta(days=3),
        ends_at=now + timezone.timedelta(days=3, hours=1),
    )
    past = EventFactory(
        created_by=facilitator,
        starts_at=now - timezone.timedelta(days=3),
        ends_at=now - timezone.timedelta(days=3) + timezone.timedelta(hours=1),
    )
    Enrollment.objects.create(event=upcoming, seeker=seeker)
    Enrollment.objects.create(event=past, seeker=seeker)

    up = seeker_client.get(reverse("enrollment-list"), {"when": "upcoming"})
    assert [e["event"]["id"] for e in up.data["results"]] == [upcoming.id]

    pa = seeker_client.get(reverse("enrollment-list"), {"when": "past"})
    assert [e["event"]["id"] for e in pa.data["results"]] == [past.id]


def test_canceled_enrollment_not_listed(seeker_client, seeker, facilitator):
    event = EventFactory(created_by=facilitator)
    Enrollment.objects.create(event=event, seeker=seeker, status="canceled")
    resp = seeker_client.get(reverse("enrollment-list"))
    assert resp.data["count"] == 0
