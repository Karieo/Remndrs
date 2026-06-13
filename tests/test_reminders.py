"""Tier 2 — natural-language reminder parsing (reminders.parse_remind_text).

dateparser's behaviour can shift across versions, so these tests pin the
contract: future expressions parse to a future ISO timestamp with the reminder
phrase stripped from the message; non-times and past times return None.
"""

from datetime import datetime, timedelta

import database as db
import reminders


def test_parse_future_relative_time():
    result = reminders.parse_remind_text('remind me tomorrow at 9am to call mom')
    assert result is not None
    fire_at, message = result
    parsed = datetime.fromisoformat(fire_at)
    assert parsed > datetime.now()
    assert 'call mom' in message.lower()


def test_parse_strips_remind_phrase_from_message():
    result = reminders.parse_remind_text('reminder: tomorrow 3pm dentist appointment')
    assert result is not None
    _fire_at, message = result
    assert 'remind' not in message.lower()
    assert 'dentist' in message.lower()


def test_parse_no_time_returns_none():
    assert reminders.parse_remind_text('just some text with no date in it') is None


def test_parse_past_time_returns_none():
    # A clearly past reference should not become a reminder.
    assert reminders.parse_remind_text('remind me yesterday to do nothing') is None


def test_parse_returns_iso_seconds_precision():
    result = reminders.parse_remind_text('remind me next monday at noon to ship')
    assert result is not None
    fire_at, _ = result
    # isoformat(timespec='seconds') → exactly one ':' in the time portion pair.
    assert datetime.fromisoformat(fire_at)  # round-trips
    assert len(fire_at.split('T')[1].split(':')) == 3


# ── check_reminders dispatch ───────────────────────────────────────────────

def _past():
    return (datetime.now() - timedelta(minutes=1)).isoformat(timespec='seconds')


def test_check_reminders_fires_due(make_user, monkeypatch):
    user = make_user('Clay')
    r = db.create_reminder(user['id'], 'ping', _past(),
                           notify_sms=False, notify_web=True)
    events = []
    monkeypatch.setattr(reminders.sse, 'push_event',
                        lambda uid, t, d: events.append((uid, t, d)))
    reminders.check_reminders()
    assert db.get_reminder(r['id'])['fired'] == 1
    assert events and events[0][1] == 'reminder'
    assert events[0][2]['message'] == 'ping'


def test_check_reminders_skips_future(make_user, monkeypatch):
    user = make_user('Clay')
    future = (datetime.now() + timedelta(hours=1)).isoformat(timespec='seconds')
    r = db.create_reminder(user['id'], 'later', future,
                           notify_sms=False, notify_web=True)
    monkeypatch.setattr(reminders.sse, 'push_event',
                        lambda *a: (_ for _ in ()).throw(AssertionError('fired early')))
    reminders.check_reminders()
    assert db.get_reminder(r['id'])['fired'] == 0


def test_check_reminders_continues_after_one_fails(make_user, monkeypatch):
    user = make_user('Clay')
    db.create_reminder(user['id'], 'bad', _past(), notify_sms=False, notify_web=True)
    r2 = db.create_reminder(user['id'], 'good', _past(), notify_sms=False, notify_web=True)
    seen = []

    def flaky(uid, t, d):
        seen.append(d['message'])
        if d['message'] == 'bad':
            raise RuntimeError('boom')
    monkeypatch.setattr(reminders.sse, 'push_event', flaky)
    reminders.check_reminders()              # must not raise
    assert set(seen) == {'bad', 'good'}      # one failure didn't abort the batch
    assert db.get_reminder(r2['id'])['fired'] == 1
