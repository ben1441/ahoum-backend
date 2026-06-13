"""The headline test: prove capacity holds under a real thundering-herd race.

Uses TransactionTestCase (not the rollback-wrapped TestCase) so each thread's
enrollment genuinely commits and the ``select_for_update`` row lock actually
serializes contending transactions. Without the lock, N threads would all read
"0 of 1 seats taken" and all insert — this test would then show multiple winners.
"""

import threading

from django.contrib.auth.models import Group
from django.db import connections
from django.test import TransactionTestCase

from apps.common.errors import AlreadyEnrolled, EventFull
from apps.enrollments.models import Enrollment
from apps.enrollments.services import enroll
from tests.factories import EventFactory, make_seeker


class CapacityRaceTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        # TransactionTestCase flushes the DB between methods, removing the role
        # groups created by the data migration; recreate them for each test.
        for name in ("seeker", "facilitator"):
            Group.objects.get_or_create(name=name)

    def test_only_capacity_many_win_the_race(self):
        seats = 3
        contenders = 12
        event = EventFactory(capacity=seats)
        seekers = [make_seeker() for _ in range(contenders)]

        barrier = threading.Barrier(contenders)
        results = {"ok": 0, "full": 0}
        lock = threading.Lock()

        def attempt(seeker):
            barrier.wait()  # release all threads at once for maximum contention
            try:
                enroll(event_id=event.id, seeker=seeker)
                with lock:
                    results["ok"] += 1
            except (EventFull, AlreadyEnrolled):
                with lock:
                    results["full"] += 1
            finally:
                connections.close_all()

        threads = [threading.Thread(target=attempt, args=(s,)) for s in seekers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        active = Enrollment.objects.filter(event=event, status="enrolled").count()
        assert active == seats, f"expected exactly {seats} enrolled, got {active}"
        assert results["ok"] == seats
        assert results["full"] == contenders - seats

    def test_same_seeker_racing_themselves_enrolls_once(self):
        """A single seeker firing many concurrent enroll requests must end up with
        exactly one active enrollment — the partial unique constraint is the guard."""
        event = EventFactory(capacity=None)
        seeker = make_seeker()
        attempts = 8

        barrier = threading.Barrier(attempts)
        wins = {"n": 0}
        lock = threading.Lock()

        def attempt():
            barrier.wait()
            try:
                enroll(event_id=event.id, seeker=seeker)
                with lock:
                    wins["n"] += 1
            except (AlreadyEnrolled, EventFull):
                pass
            finally:
                connections.close_all()

        threads = [threading.Thread(target=attempt) for _ in range(attempts)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        active = Enrollment.objects.filter(event=event, seeker=seeker, status="enrolled").count()
        assert active == 1
        assert wins["n"] == 1
