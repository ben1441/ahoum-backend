from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.enrollments.models import Enrollment

from . import emails
from .models import EmailLog


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def send_otp_email_task(self, user_id: int, code: str):
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return
    emails.send_otp_email(user, code)


def _send_once(enrollment: Enrollment, kind: str, send_fn) -> bool:
    """Send an email at most once per (enrollment, kind).

    The EmailLog row is the idempotency key: get_or_create + the unique constraint
    mean concurrent or repeated task runs can never double-send. We claim the row
    first, then send; if the send fails the row's sent_at stays null and a later
    run retries it (without creating a duplicate).
    """
    try:
        with transaction.atomic():
            log, created = EmailLog.objects.get_or_create(enrollment=enrollment, kind=kind)
    except IntegrityError:
        return False  # claimed by a concurrent run
    if log.sent_at is not None:
        return False  # already sent
    send_fn(enrollment)
    log.sent_at = timezone.now()
    log.save(update_fields=["sent_at", "updated_at"])
    return True


@shared_task
def send_enrollment_follow_ups() -> int:
    """Follow-up email to seekers who enrolled at least an hour ago."""
    cutoff = timezone.now() - settings.ENROLLMENT_FOLLOW_UP_DELAY
    enrollments = (
        Enrollment.objects.filter(status=Enrollment.Status.ENROLLED, created_at__lte=cutoff)
        .exclude(email_logs__kind=EmailLog.Kind.FOLLOW_UP)
        .select_related("event", "seeker")
    )
    sent = 0
    for enrollment in enrollments:
        if _send_once(enrollment, EmailLog.Kind.FOLLOW_UP, emails.send_follow_up_email):
            sent += 1
    return sent


@shared_task
def send_event_reminders() -> int:
    """Reminder email to seekers whose event starts within the next hour."""
    now = timezone.now()
    window_end = now + settings.EVENT_REMINDER_WINDOW
    enrollments = (
        Enrollment.objects.filter(
            status=Enrollment.Status.ENROLLED,
            event__starts_at__gt=now,
            event__starts_at__lte=window_end,
        )
        .exclude(email_logs__kind=EmailLog.Kind.REMINDER)
        .select_related("event", "seeker")
    )
    sent = 0
    for enrollment in enrollments:
        if _send_once(enrollment, EmailLog.Kind.REMINDER, emails.send_reminder_email):
            sent += 1
    return sent
