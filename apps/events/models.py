from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


class Event(TimeStampedModel):
    title = models.CharField(max_length=255)
    description = models.TextField()
    language = models.CharField(max_length=50)
    location = models.CharField(max_length=255)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(null=True, blank=True)  # NULL => unlimited
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="events_created"
    )

    class Meta:
        indexes = [
            models.Index(fields=["starts_at"]),
            models.Index(fields=["language"]),
            models.Index(fields=["location"]),
            models.Index(fields=["location", "starts_at"]),
            GinIndex(
                SearchVector("title", "description", config="english"),
                name="event_fts_gin",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="event_ends_after_starts",
            ),
            models.CheckConstraint(
                condition=models.Q(capacity__isnull=True) | models.Q(capacity__gte=1),
                name="event_capacity_positive",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def has_started(self) -> bool:
        return timezone.now() >= self.starts_at

    @property
    def has_ended(self) -> bool:
        return timezone.now() >= self.ends_at
