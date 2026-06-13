import uuid

import factory
from django.contrib.auth.models import Group, User
from django.utils import timezone

from apps.accounts.models import Profile, Role
from apps.enrollments.models import Enrollment
from apps.events.models import Event


def make_user(*, role=Role.SEEKER, verified=True, password="pass1234!", email=None, **kwargs):
    """Create a User fully wired up with a Profile and role-group membership.

    Lives as a plain helper rather than a factory because User creation here is
    bespoke: an opaque username (signup never accepts one), a Profile, and Django
    group membership for RBAC.
    """
    user = User(
        username=uuid.uuid4().hex[:30],
        email=email or f"{uuid.uuid4().hex[:10]}@example.com",
        **kwargs,
    )
    user.set_password(password)
    user.save()
    Profile.objects.create(
        user=user, role=role, email_verified_at=timezone.now() if verified else None
    )
    user.groups.add(Group.objects.get(name=role))
    return user


def make_seeker(**kwargs):
    return make_user(role=Role.SEEKER, **kwargs)


def make_facilitator(**kwargs):
    return make_user(role=Role.FACILITATOR, **kwargs)


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event

    title = factory.Sequence(lambda n: f"Event {n}")
    description = factory.Faker("paragraph")
    language = "english"
    location = "online"
    starts_at = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=7))
    ends_at = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=7, hours=2))
    capacity = None
    created_by = factory.LazyFunction(make_facilitator)


class EnrollmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Enrollment

    event = factory.SubFactory(EventFactory)
    seeker = factory.LazyFunction(make_seeker)
    status = Enrollment.Status.ENROLLED
