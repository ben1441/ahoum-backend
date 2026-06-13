from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.events.models import Event


class Enrollment(TimeStampedModel):
    """A seeker's enrollment in an event.

    Cancellations flip ``status`` instead of deleting the row (audit trail).
    The partial unique constraint is the database-level guarantee that a seeker
    can hold at most one *active* enrollment per event, while still allowing
    re-enrollment after a cancellation.
    """

    class Status(models.TextChoices):
        ENROLLED = "enrolled", "Enrolled"
        CANCELED = "canceled", "Canceled"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="enrollments")
    seeker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ENROLLED)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "seeker"],
                condition=models.Q(status="enrolled"),
                name="uniq_active_enrollment_per_event",
            ),
        ]
        indexes = [
            models.Index(fields=["seeker", "status"]),
            models.Index(fields=["event", "status"]),
        ]

    def __str__(self):
        return f"{self.seeker.email} -> {self.event.title} ({self.status})"
