from django.db import models

from apps.common.models import TimeStampedModel
from apps.enrollments.models import Enrollment


class EmailLog(TimeStampedModel):
    """Record of a scheduled email sent for an enrollment.

    The unique constraint is what makes the beat tasks idempotent: a follow-up or
    reminder can be sent at most once per enrollment, no matter how often the task
    runs, retries, or overlaps with itself.
    """

    class Kind(models.TextChoices):
        FOLLOW_UP = "follow_up", "Follow-up"
        REMINDER = "reminder", "Reminder"

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="email_logs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "kind"], name="uniq_email_per_kind"),
        ]

    def __str__(self):
        return f"{self.kind} for enrollment {self.enrollment_id}"
