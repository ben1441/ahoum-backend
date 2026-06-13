from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsEventOwnerOrReadOnly, IsFacilitator, IsSeeker
from apps.enrollments import services as enrollment_services
from apps.enrollments.serializers import EnrollmentSerializer

from .filters import EventFilter
from .models import Event
from .serializers import EventSerializer, MyEventSerializer


class EventViewSet(viewsets.ModelViewSet):
    """Event search (any authenticated user) + CRUD (facilitators, owner-only writes)."""

    serializer_class = EventSerializer
    filterset_class = EventFilter
    ordering_fields = ["starts_at", "ends_at", "created_at", "title"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "mine"):
            return [IsAuthenticated(), IsFacilitator(), IsEventOwnerOrReadOnly()]
        if self.action in ("enroll", "cancel"):
            return [IsAuthenticated(), IsSeeker()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = Event.objects.select_related("created_by")
        if self.action == "list" and not self.request.query_params.get("ordering"):
            # Default ordering: upcoming events first (soonest at the top), past events after.
            qs = qs.annotate(
                _is_past=Case(
                    When(starts_at__gt=timezone.now(), then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("_is_past", "starts_at")
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"], serializer_class=MyEventSerializer)
    def mine(self, request):
        """Facilitator's own events with enrollment totals and remaining seats."""
        qs = (
            Event.objects.filter(created_by=request.user)
            .annotate(
                total_enrollments=Count("enrollments", filter=Q(enrollments__status="enrolled"))
            )
            .order_by("-starts_at")
        )
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["post"], serializer_class=EnrollmentSerializer)
    def enroll(self, request, pk=None):
        """Seeker enrolls in the event (capacity- and concurrency-safe)."""
        enrollment = enrollment_services.enroll(event_id=pk, seeker=request.user)
        serializer = self.get_serializer(enrollment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], serializer_class=EnrollmentSerializer)
    def cancel(self, request, pk=None):
        """Seeker cancels their own active enrollment."""
        enrollment = enrollment_services.cancel(event_id=pk, seeker=request.user)
        serializer = self.get_serializer(enrollment)
        return Response(serializer.data)
