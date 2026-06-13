from rest_framework import serializers

from apps.events.serializers import EventSerializer

from .models import Enrollment


class EnrollmentSerializer(serializers.ModelSerializer):
    event = EventSerializer(read_only=True)

    class Meta:
        model = Enrollment
        fields = ["id", "event", "status", "created_at", "canceled_at"]
