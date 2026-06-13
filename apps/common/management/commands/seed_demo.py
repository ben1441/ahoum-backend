"""Seed a small but realistic demo dataset for local exploration and the deployed
demo. Idempotent: safe to run repeatedly (keys off well-known demo emails)."""

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Profile, Role
from apps.enrollments.models import Enrollment
from apps.events.models import Event

PASSWORD = "demopass123!"


class Command(BaseCommand):
    help = "Create demo facilitators, seekers, events and enrollments."

    @transaction.atomic
    def handle(self, *args, **options):
        for name in (Role.SEEKER, Role.FACILITATOR):
            Group.objects.get_or_create(name=name)

        facilitator = self._user("facilitator@demo.ahoum.com", Role.FACILITATOR)
        seeker = self._user("seeker@demo.ahoum.com", Role.SEEKER)
        seeker2 = self._user("seeker2@demo.ahoum.com", Role.SEEKER)

        now = timezone.now()
        specs = [
            (
                "Sunrise Yoga",
                "Gentle morning vinyasa for all levels.",
                "english",
                "Goa",
                now + timezone.timedelta(days=3),
                20,
            ),
            (
                "Sound Healing Circle",
                "Tibetan bowls and deep relaxation.",
                "english",
                "Pune",
                now + timezone.timedelta(days=7),
                2,
            ),
            (
                "Breathwork Intensive",
                "Guided pranayama session.",
                "hindi",
                "Online",
                now + timezone.timedelta(hours=0, minutes=45),
                None,
            ),
            (
                "Past Meditation Retreat",
                "A weekend of silence.",
                "english",
                "Rishikesh",
                now - timezone.timedelta(days=10),
                30,
            ),
        ]
        events = []
        for title, desc, lang, loc, starts, cap in specs:
            event, _ = Event.objects.update_or_create(
                title=title,
                created_by=facilitator,
                defaults={
                    "description": desc,
                    "language": lang,
                    "location": loc,
                    "starts_at": starts,
                    "ends_at": starts + timezone.timedelta(hours=2),
                    "capacity": cap,
                },
            )
            events.append(event)

        # A couple of enrollments (upcoming + past) for the demo seeker.
        Enrollment.objects.get_or_create(
            event=events[0], seeker=seeker, status=Enrollment.Status.ENROLLED
        )
        Enrollment.objects.get_or_create(
            event=events[3], seeker=seeker, status=Enrollment.Status.ENROLLED
        )
        Enrollment.objects.get_or_create(
            event=events[1], seeker=seeker2, status=Enrollment.Status.ENROLLED
        )

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"  Facilitator: {facilitator.email} / {PASSWORD}")
        self.stdout.write(f"  Seeker:      {seeker.email} / {PASSWORD}")

    def _user(self, email: str, role: str) -> User:
        user, created = User.objects.get_or_create(
            email=email, defaults={"username": email.split("@")[0]}
        )
        if created:
            user.set_password(PASSWORD)
            user.save()
        Profile.objects.update_or_create(
            user=user, defaults={"role": role, "email_verified_at": timezone.now()}
        )
        user.groups.add(Group.objects.get(name=role))
        return user
