from rest_framework import serializers

from .models import Event


class EventSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "language",
            "location",
            "starts_at",
            "ends_at",
            "capacity",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_capacity(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Capacity must be at least 1.")
        return value

    def validate(self, attrs):
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError({"ends_at": "ends_at must be after starts_at."})

        # Don't let an update strand already-enrolled seekers beyond capacity.
        capacity = attrs.get("capacity", getattr(self.instance, "capacity", None))
        if self.instance is not None and capacity is not None:
            active = self.instance.enrollments.filter(status="enrolled").count()
            if capacity < active:
                raise serializers.ValidationError(
                    {"capacity": f"Capacity cannot be below current enrollments ({active})."}
                )
        return attrs


class MyEventSerializer(EventSerializer):
    """Facilitator dashboard view: includes enrollment counts and remaining seats.

    ``total_enrollments`` is annotated by the view (single query, no N+1).
    """

    total_enrollments = serializers.IntegerField(read_only=True)
    available_seats = serializers.SerializerMethodField()

    class Meta(EventSerializer.Meta):
        fields = EventSerializer.Meta.fields + ["total_enrollments", "available_seats"]

    def get_available_seats(self, obj) -> int | None:
        if obj.capacity is None:
            return None  # unlimited
        return max(obj.capacity - obj.total_enrollments, 0)
