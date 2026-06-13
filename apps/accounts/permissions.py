"""Role-based access control via Django Groups.

Signup places every user in a ``seeker`` or ``facilitator`` group (created by a
data migration); these DRF permission classes gate endpoints on membership.
Group names are cached per request/user instance to avoid repeated queries.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Role


def user_in_role(user, role: str) -> bool:
    if not user.is_authenticated:
        return False
    cached = getattr(user, "_role_names", None)
    if cached is None:
        cached = set(user.groups.values_list("name", flat=True))
        user._role_names = cached
    return role in cached


class IsSeeker(BasePermission):
    message = "Only seekers can perform this action."

    def has_permission(self, request, view):
        return user_in_role(request.user, Role.SEEKER)


class IsFacilitator(BasePermission):
    message = "Only facilitators can perform this action."

    def has_permission(self, request, view):
        return user_in_role(request.user, Role.FACILITATOR)


class IsEventOwnerOrReadOnly(BasePermission):
    """Anyone authenticated can read; only the creating facilitator can modify."""

    message = "Only the event's creator can modify it."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.created_by_id == request.user.id
