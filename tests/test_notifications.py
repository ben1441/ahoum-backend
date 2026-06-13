"""Scheduled-mail idempotency: the EmailLog unique constraint guarantees each
follow-up/reminder is sent at most once, no matter how often the beat task runs."""

import pytest
from django.core import mail
from django.utils import timezone

from apps.enrollments.models import Enrollment
from apps.notifications.models import EmailLog
from apps.notifications.tasks import send_enrollment_follow_ups, send_event_reminders
from tests.factories import EventFactory, make_seeker

pytestmark = pytest.mark.django_db


def _enroll(event, seeker=None):
    return Enrollment.objects.create(event=event, seeker=seeker or make_seeker())


# --- Follow-up --------------------------------------------------------------


def test_follow_up_sent_after_one_hour(facilitator):
    event = EventFactory(created_by=facilitator)
    enrollment = _enroll(event)
    # Backdate the enrollment past the 1h threshold.
    Enrollment.objects.filter(pk=enrollment.pk).update(
        created_at=timezone.now() - timezone.timedelta(hours=2)
    )

    sent = send_enrollment_follow_ups()
    assert sent == 1
    assert len(mail.outbox) == 1
    assert EmailLog.objects.filter(enrollment=enrollment, kind="follow_up").exists()


def test_follow_up_not_sent_before_one_hour(facilitator):
    event = EventFactory(created_by=facilitator)
    _enroll(event)  # just enrolled, created_at = now
    assert send_enrollment_follow_ups() == 0
    assert len(mail.outbox) == 0


def test_follow_up_is_idempotent_across_runs(facilitator):
    event = EventFactory(created_by=facilitator)
    enrollment = _enroll(event)
    Enrollment.objects.filter(pk=enrollment.pk).update(
        created_at=timezone.now() - timezone.timedelta(hours=2)
    )

    assert send_enrollment_follow_ups() == 1
    # Running the task again must NOT send a second email.
    assert send_enrollment_follow_ups() == 0
    assert len(mail.outbox) == 1
    assert EmailLog.objects.filter(enrollment=enrollment, kind="follow_up").count() == 1


# --- Reminder ---------------------------------------------------------------


def test_reminder_sent_within_hour_window(facilitator):
    event = EventFactory(
        created_by=facilitator,
        starts_at=timezone.now() + timezone.timedelta(minutes=30),
        ends_at=timezone.now() + timezone.timedelta(minutes=90),
    )
    enrollment = _enroll(event)
    assert send_event_reminders() == 1
    assert EmailLog.objects.filter(enrollment=enrollment, kind="reminder").exists()


def test_reminder_not_sent_outside_window(facilitator):
    event = EventFactory(
        created_by=facilitator,
        starts_at=timezone.now() + timezone.timedelta(hours=5),
        ends_at=timezone.now() + timezone.timedelta(hours=6),
    )
    _enroll(event)
    assert send_event_reminders() == 0


def test_reminder_is_idempotent_across_runs(facilitator):
    event = EventFactory(
        created_by=facilitator,
        starts_at=timezone.now() + timezone.timedelta(minutes=30),
        ends_at=timezone.now() + timezone.timedelta(minutes=90),
    )
    _enroll(event)
    assert send_event_reminders() == 1
    assert send_event_reminders() == 0
    assert len(mail.outbox) == 1


def test_canceled_enrollment_gets_no_mail(facilitator):
    event = EventFactory(
        created_by=facilitator,
        starts_at=timezone.now() + timezone.timedelta(minutes=30),
        ends_at=timezone.now() + timezone.timedelta(minutes=90),
    )
    enrollment = _enroll(event)
    enrollment.status = "canceled"
    enrollment.save(update_fields=["status"])
    assert send_event_reminders() == 0
