from django.utils import timezone
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from apps.accounts.permissions import IsSeeker

from .models import Enrollment
from .serializers import EnrollmentSerializer


class EnrollmentViewSet(ListModelMixin, GenericViewSet):
    """Seeker-facing enrollment listing.

    ``GET /enrollments/?when=upcoming|past`` splits on whether the event has
    already ended. Default (no ``when``) returns all active enrollments,
    soonest first. The enroll/cancel actions live on the event resource
    (``/events/{id}/enroll`` and ``/cancel``) since they act on an event.
    """

    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated, IsSeeker]
    queryset = Enrollment.objects.none()  # for schema introspection

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Enrollment.objects.none()
        qs = Enrollment.objects.filter(
            seeker=self.request.user, status=Enrollment.Status.ENROLLED
        ).select_related("event", "event__created_by")
        when = self.request.query_params.get("when")
        now = timezone.now()
        if when == "past":
            return qs.filter(event__ends_at__lt=now).order_by("-event__starts_at")
        if when == "upcoming":
            return qs.filter(event__ends_at__gte=now).order_by("event__starts_at")
        return qs.order_by("event__starts_at")
