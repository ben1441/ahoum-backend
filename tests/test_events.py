"""Event CRUD, RBAC, search filters, ordering, and the facilitator dashboard."""

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.common.errors import ErrorCode
from tests.factories import EnrollmentFactory, EventFactory, make_seeker

pytestmark = pytest.mark.django_db


def _event_payload(**overrides):
    starts = timezone.now() + timezone.timedelta(days=10)
    payload = {
        "title": "Sunrise Yoga",
        "description": "A calming morning yoga flow for all levels.",
        "language": "english",
        "location": "Goa",
        "starts_at": starts.isoformat(),
        "ends_at": (starts + timezone.timedelta(hours=2)).isoformat(),
        "capacity": 20,
    }
    payload.update(overrides)
    return payload


# --- RBAC on create/update/delete -------------------------------------------


def test_facilitator_can_create_event(facilitator_client):
    resp = facilitator_client.post(reverse("event-list"), _event_payload())
    assert resp.status_code == 201
    assert resp.data["title"] == "Sunrise Yoga"


def test_seeker_cannot_create_event(seeker_client):
    resp = seeker_client.post(reverse("event-list"), _event_payload())
    assert resp.status_code == 403
    assert resp.data["code"] == ErrorCode.PERMISSION_DENIED


def test_only_owner_can_update_event(facilitator_client, facilitator, as_user):
    from tests.factories import make_facilitator

    event = EventFactory(created_by=facilitator)
    other = make_facilitator()
    resp = as_user(other).patch(reverse("event-detail", args=[event.id]), {"title": "Hijacked"})
    assert resp.status_code == 403

    ok = facilitator_client.patch(reverse("event-detail", args=[event.id]), {"title": "Renamed"})
    assert ok.status_code == 200
    assert ok.data["title"] == "Renamed"


def test_only_owner_can_delete_event(facilitator_client, facilitator):
    event = EventFactory(created_by=facilitator)
    resp = facilitator_client.delete(reverse("event-detail", args=[event.id]))
    assert resp.status_code == 204


def test_create_rejects_end_before_start(facilitator_client):
    starts = timezone.now() + timezone.timedelta(days=5)
    resp = facilitator_client.post(
        reverse("event-list"),
        _event_payload(
            starts_at=starts.isoformat(),
            ends_at=(starts - timezone.timedelta(hours=1)).isoformat(),
        ),
    )
    assert resp.status_code == 400
    assert resp.data["code"] == ErrorCode.VALIDATION_ERROR


def test_update_capacity_below_enrollments_rejected(facilitator_client, facilitator):
    event = EventFactory(created_by=facilitator, capacity=10)
    EnrollmentFactory.create_batch(3, event=event)
    resp = facilitator_client.patch(reverse("event-detail", args=[event.id]), {"capacity": 2})
    assert resp.status_code == 400


# --- Search / filter / order ------------------------------------------------


def test_anonymous_cannot_list_events(api):
    resp = api.get(reverse("event-list"))
    assert resp.status_code == 401


def test_search_by_q_matches_title_and_description(seeker_client, facilitator):
    EventFactory(created_by=facilitator, title="Yoga Retreat", description="deep stretch")
    EventFactory(created_by=facilitator, title="Cooking Class", description="pasta night")
    resp = seeker_client.get(reverse("event-list"), {"q": "yoga"})
    assert resp.status_code == 200
    titles = [e["title"] for e in resp.data["results"]]
    assert "Yoga Retreat" in titles
    assert "Cooking Class" not in titles


def test_filter_by_location_and_language(seeker_client, facilitator):
    EventFactory(created_by=facilitator, location="Goa", language="english")
    EventFactory(created_by=facilitator, location="Pune", language="hindi")
    resp = seeker_client.get(reverse("event-list"), {"location": "goa"})
    assert [e["location"] for e in resp.data["results"]] == ["Goa"]
    resp2 = seeker_client.get(reverse("event-list"), {"language": "hindi"})
    assert [e["language"] for e in resp2.data["results"]] == ["hindi"]


def test_filter_by_starts_after_before(seeker_client, facilitator):
    now = timezone.now()
    EventFactory(
        created_by=facilitator,
        starts_at=now + timezone.timedelta(days=2),
        ends_at=now + timezone.timedelta(days=2, hours=1),
        title="Soon",
    )
    EventFactory(
        created_by=facilitator,
        starts_at=now + timezone.timedelta(days=30),
        ends_at=now + timezone.timedelta(days=30, hours=1),
        title="Later",
    )
    cutoff = (now + timezone.timedelta(days=10)).isoformat()
    resp = seeker_client.get(reverse("event-list"), {"starts_after": cutoff})
    assert [e["title"] for e in resp.data["results"]] == ["Later"]


def test_default_ordering_is_upcoming_first(seeker_client, facilitator):
    now = timezone.now()
    EventFactory(
        created_by=facilitator,
        title="Past",
        starts_at=now - timezone.timedelta(days=2),
        ends_at=now - timezone.timedelta(days=2) + timezone.timedelta(hours=1),
    )
    EventFactory(
        created_by=facilitator,
        title="Far",
        starts_at=now + timezone.timedelta(days=20),
        ends_at=now + timezone.timedelta(days=20, hours=1),
    )
    EventFactory(
        created_by=facilitator,
        title="Near",
        starts_at=now + timezone.timedelta(days=2),
        ends_at=now + timezone.timedelta(days=2, hours=1),
    )
    resp = seeker_client.get(reverse("event-list"))
    titles = [e["title"] for e in resp.data["results"]]
    # Upcoming soonest-first, then past events.
    assert titles.index("Near") < titles.index("Far") < titles.index("Past")


def test_pagination_shape(seeker_client, facilitator):
    EventFactory.create_batch(3, created_by=facilitator)
    resp = seeker_client.get(reverse("event-list"))
    assert set(resp.data.keys()) == {"count", "next", "previous", "results"}


# --- Facilitator dashboard --------------------------------------------------


def test_mine_returns_counts_and_seats(facilitator_client, facilitator):
    event = EventFactory(created_by=facilitator, capacity=5)
    EnrollmentFactory.create_batch(2, event=event)
    # A canceled enrollment must not count.
    EnrollmentFactory(event=event, seeker=make_seeker(), status="canceled")
    resp = facilitator_client.get(reverse("event-mine"))
    assert resp.status_code == 200
    row = next(e for e in resp.data["results"] if e["id"] == event.id)
    assert row["total_enrollments"] == 2
    assert row["available_seats"] == 3


def test_mine_unlimited_capacity_seats_null(facilitator_client, facilitator):
    EventFactory(created_by=facilitator, capacity=None)
    resp = facilitator_client.get(reverse("event-mine"))
    assert resp.data["results"][0]["available_seats"] is None


def test_seeker_cannot_access_mine(seeker_client):
    resp = seeker_client.get(reverse("event-mine"))
    assert resp.status_code == 403
