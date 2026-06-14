"""Recurring reminders: recurrence parsing, next-occurrence math, and the
re-scheduling that happens when a recurring reminder fires.
"""

from datetime import datetime, timedelta

import database as db
import mcp_server
import reminders


def _past():
    return (datetime.now() - timedelta(minutes=1)).isoformat(timespec='seconds')


# ── parse_recurrence / normalize_recurrence ────────────────────────────────

def test_parse_recurrence_keywords():
    assert reminders.parse_recurrence('daily') == 'FREQ=DAILY'
    assert reminders.parse_recurrence('every day') == 'FREQ=DAILY'
    assert reminders.parse_recurrence('weekly') == 'FREQ=WEEKLY'
    assert reminders.parse_recurrence('monthly') == 'FREQ=MONTHLY'
    assert reminders.parse_recurrence('yearly') == 'FREQ=YEARLY'
    assert reminders.parse_recurrence('weekdays') == 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR'
    assert reminders.parse_recurrence('every weekday') == 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR'


def test_parse_recurrence_every_weekday_name():
    assert reminders.parse_recurrence('every monday') == 'FREQ=WEEKLY;BYDAY=MO'
    assert reminders.parse_recurrence('every Friday') == 'FREQ=WEEKLY;BYDAY=FR'


def test_parse_recurrence_none():
    assert reminders.parse_recurrence('') is None
    assert reminders.parse_recurrence('just once tomorrow') is None


def test_normalize_recurrence_accepts_keyword_and_rrule():
    assert reminders.normalize_recurrence('daily') == 'FREQ=DAILY'
    assert reminders.normalize_recurrence('FREQ=WEEKLY;BYDAY=TU') == 'FREQ=WEEKLY;BYDAY=TU'
    assert reminders.normalize_recurrence('') is None
    assert reminders.normalize_recurrence('gibberish nonsense') is None


# ── next_recurrence ─────────────────────────────────────────────────────────

def test_next_recurrence_is_future_and_keeps_time_of_day():
    # A daily reminder anchored at 09:00 yesterday → next is a future 09:00.
    anchor = (datetime.now() - timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0)
    nxt = reminders.next_recurrence('FREQ=DAILY', anchor.isoformat(timespec='seconds'))
    parsed = datetime.fromisoformat(nxt)
    assert parsed > datetime.now()
    assert (parsed.hour, parsed.minute) == (9, 0)


def test_next_recurrence_none_for_blank():
    assert reminders.next_recurrence(None, _past()) is None


# ── dispatch reschedules a recurring reminder ───────────────────────────────

def test_dispatch_schedules_next_occurrence(make_user, monkeypatch):
    user = make_user('Clay')
    anchor = (datetime.now() - timedelta(minutes=1)).isoformat(timespec='seconds')
    r = db.create_reminder(user['id'], 'standup', anchor,
                           notify_sms=False, notify_web=True, recurrence='FREQ=DAILY')
    monkeypatch.setattr(reminders.sse, 'push_event', lambda *a: None)

    reminders.check_reminders()

    # The fired one stays fired; a fresh future occurrence is created.
    assert db.get_reminder(r['id'])['fired'] == 1
    upcoming = db.list_reminders(user['id'])
    assert len(upcoming) == 1
    nxt = upcoming[0]
    assert nxt['id'] != r['id']
    assert nxt['recurrence'] == 'FREQ=DAILY'
    assert datetime.fromisoformat(nxt['fire_at']) > datetime.now()


def test_dispatch_no_reschedule_for_oneoff(make_user, monkeypatch):
    user = make_user('Clay')
    db.create_reminder(user['id'], 'once', _past(), notify_sms=False, notify_web=True)
    monkeypatch.setattr(reminders.sse, 'push_event', lambda *a: None)
    reminders.check_reminders()
    assert db.list_reminders(user['id']) == []   # nothing re-scheduled


# ── HTTP + MCP surfaces ──────────────────────────────────────────────────────

def test_create_reminder_route_stores_recurrence(client, make_user):
    user = make_user('Clay')
    client.post('/api/auth/login', json={'login': 'Clay', 'password': 'pw'})
    future = (datetime.now() + timedelta(hours=1)).isoformat(timespec='seconds')
    resp = client.post('/api/reminders',
                       json={'message': 'gym', 'fire_at': future, 'recurrence': 'weekdays'})
    assert resp.status_code == 201
    assert resp.get_json()['recurrence'] == 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR'


def test_mcp_add_reminder_repeat(make_user):
    user = make_user('Clay')
    out = mcp_server._tool_add_reminder(
        user, {'when': 'tomorrow at 9am', 'message': 'vitamins', 'repeat': 'daily'})
    assert 'repeats daily' in out
    rem = db.list_reminders(user['id'])[0]
    assert rem['recurrence'] == 'FREQ=DAILY'


def test_mcp_list_reminders_shows_recurrence(make_user):
    user = make_user('Clay')
    future = (datetime.now() + timedelta(hours=2)).isoformat(timespec='seconds')
    db.create_reminder(user['id'], 'water plants', future, recurrence='FREQ=WEEKLY')
    out = mcp_server._tool_list_reminders(user, {})
    assert 'repeats weekly' in out
