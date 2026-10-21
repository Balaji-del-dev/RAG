import threading

import pytest
from django.db import connection, transaction
from django.utils import timezone

from apps.core import outbox
from apps.core.models import OutboxEvent


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(outbox.celery_app, "send_task", lambda name, **kwargs: calls.append((name, kwargs)))
    return calls


def test_emit_rejects_unknown_event_types(make_user):
    with pytest.raises(ValueError):
        outbox.emit("nope.unknown", make_user())


def test_dispatch_sends_each_pending_row_once_and_marks_it(make_user, sent):
    user = make_user()
    events = [outbox.emit("core.ping", user, {"n": n}) for n in range(3)]
    assert outbox.dispatch_batch() == 3
    assert outbox.dispatch_batch() == 0
    assert [name for name, _ in sent] == ["core.ping"] * 3
    assert [kwargs["task_id"] for _, kwargs in sent] == [f"outbox-{e.pk}" for e in events]
    assert set(OutboxEvent.objects.values_list("status", flat=True)) == {"DISPATCHED"}


def test_a_broker_failure_backs_off_and_keeps_the_row_pending(make_user, monkeypatch):
    def broken(*args, **kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(outbox.celery_app, "send_task", broken)
    event = outbox.emit("core.ping", make_user())
    assert outbox.dispatch_batch() == 1
    event.refresh_from_db()
    assert event.status == "PENDING"
    assert event.attempts == 1
    assert event.available_at > timezone.now()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_dispatchers_never_claim_the_same_row(make_user, sent):
    user = make_user()
    for n in range(10):
        outbox.emit("core.ping", user, {"n": n})

    held_ids: list[int] = []
    claimed, release = threading.Event(), threading.Event()

    def other_dispatcher():
        try:
            with transaction.atomic():
                rows = OutboxEvent.objects.select_for_update(skip_locked=True).filter(status="PENDING").order_by("id")[:5]
                held_ids.extend(row.pk for row in rows)
                claimed.set()
                release.wait(10)
        finally:
            connection.close()

    thread = threading.Thread(target=other_dispatcher)
    thread.start()
    assert claimed.wait(10)
    try:
        assert outbox.dispatch_batch() == 5
    finally:
        release.set()
        thread.join()

    sent_ids = {int(kwargs["task_id"].removeprefix("outbox-")) for _, kwargs in sent}
    assert len(held_ids) == 5
    assert sent_ids.isdisjoint(held_ids)
