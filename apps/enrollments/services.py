"""Enrollment business logic — the concurrency-sensitive part of the system.

``enroll`` takes a row lock on the event (``select_for_update``) so concurrent
requests for the last seat serialize: only one transaction counts seats and
inserts while others wait. The partial unique constraint on Enrollment is the
database-level backstop against double-enrollment even if application code
regresses.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.common import errors
from apps.events.models import Event

from .models import Enrollment


@transaction.atomic
def enroll(*, event_id: int, seeker) -> Enrollment:
    event = Event.objects.select_for_update().filter(pk=event_id).first()
    if event is None:
        raise NotFound("Event not found.")

    if timezone.now() >= event.starts_at:
        raise errors.EventAlreadyStarted()

    active = event.enrollments.filter(status=Enrollment.Status.ENROLLED)
    if active.filter(seeker=seeker).exists():
        raise errors.AlreadyEnrolled()

    if event.capacity is not None and active.count() >= event.capacity:
        raise errors.EventFull()

    try:
        return Enrollment.objects.create(event=event, seeker=seeker)
    except IntegrityError:
        # Backstop: the partial unique constraint fired despite the pre-check.
        raise errors.AlreadyEnrolled() from None


@transaction.atomic
def cancel(*, event_id: int, seeker) -> Enrollment:
    enrollment = (
        Enrollment.objects.select_for_update()
        .filter(event_id=event_id, seeker=seeker, status=Enrollment.Status.ENROLLED)
        .first()
    )
    if enrollment is None:
        if not Event.objects.filter(pk=event_id).exists():
            raise NotFound("Event not found.")
        raise errors.NotEnrolled()

    enrollment.status = Enrollment.Status.CANCELED
    enrollment.canceled_at = timezone.now()
    enrollment.save(update_fields=["status", "canceled_at", "updated_at"])
    return enrollment
