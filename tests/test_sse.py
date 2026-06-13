"""Tier 3 — SSE subscription registry and fan-out (sse.py).

Per-connection queues; ``push_note_event`` fans shared-feed notes out to every
user while keeping private notes to their owner.
"""

import pytest

import sse


@pytest.fixture(autouse=True)
def clear_subscribers():
    sse._subscribers.clear()
    yield
    sse._subscribers.clear()


# ── subscribe / unsubscribe / push_event ───────────────────────────────────

def test_subscribe_returns_queue_and_registers():
    q = sse.subscribe('u1')
    assert sse._subscribers['u1'] == [q]


def test_push_event_delivers_to_all_open_streams_for_user():
    q1 = sse.subscribe('u1')
    q2 = sse.subscribe('u1')      # second tab/device
    sse.push_event('u1', 'ping', {'x': 1})
    assert q1.get_nowait() == {'type': 'ping', 'data': {'x': 1}}
    assert q2.get_nowait() == {'type': 'ping', 'data': {'x': 1}}


def test_push_event_isolated_between_users():
    q1 = sse.subscribe('u1')
    q2 = sse.subscribe('u2')
    sse.push_event('u1', 'ping', {})
    assert not q1.empty()
    assert q2.empty()


def test_unsubscribe_removes_queue():
    q = sse.subscribe('u1')
    sse.unsubscribe('u1', q)
    assert sse._subscribers.get('u1') == []
    # Safe to unsubscribe twice / unknown queue.
    sse.unsubscribe('u1', q)
    sse.unsubscribe('nope', q)


def test_push_event_to_no_subscribers_is_noop():
    sse.push_event('ghost', 'ping', {})   # must not raise


# ── push_note_event fan-out ────────────────────────────────────────────────

def test_private_note_only_reaches_owner(make_user):
    alice = make_user('Alice')
    bob = make_user('Bob')
    qa = sse.subscribe(alice['id'])
    qb = sse.subscribe(bob['id'])
    sse.push_note_event('note_created', {'feed': 'private', 'user_id': alice['id']})
    assert not qa.empty()
    assert qb.empty()


def test_shared_note_broadcasts_to_all_users(make_user):
    alice = make_user('Alice')
    bob = make_user('Bob')
    qa = sse.subscribe(alice['id'])
    qb = sse.subscribe(bob['id'])
    sse.push_note_event('note_created', {'feed': 'shared', 'user_id': alice['id']})
    assert qa.get_nowait()['type'] == 'note_created'
    assert qb.get_nowait()['type'] == 'note_created'
