"""Snooze: re-arm a fired reminder for a later time.

Covers the db helper, the HTTP route (presets + minutes + ownership), and the
MCP tool. A snoozed reminder must clear `fired` and `acknowledged` so the 60s
dispatcher runs it again and the banner can resurface when it next fires.
"""

from datetime import datetime, timedelta

import database as db
import mcp_server


def _past():
    return (datetime.now() - timedelta(minutes=1)).isoformat(timespec='seconds')


# ── db.snooze_reminder ─────────────────────────────────────────────────────

def test_snooze_clears_fired_and_acknowledged(make_user):
    user = make_user('Clay')
    r = db.create_reminder(user['id'], 'milk', _past())
    db.mark_reminder_fired(r['id'])
    db.acknowledge_reminder(r['id'])
    assert db.get_reminder(r['id'])['fired'] == 1
    assert db.get_reminder(r['id'])['acknowledged'] == 1

    future = (datetime.now() + timedelta(hours=1)).isoformat(timespec='seconds')
    db.snooze_reminder(r['id'], future)

    row = db.get_reminder(r['id'])
    assert row['fired'] == 0
    assert row['acknowledged'] == 0
    assert row['fire_at'] == future


def test_snoozed_reminder_drops_out_of_pending(make_user):
    user = make_user('Clay')
    r = db.create_reminder(user['id'], 'milk', _past())
    db.mark_reminder_fired(r['id'])
    assert any(x['id'] == r['id'] for x in db.pending_reminders(user['id']))
    db.snooze_reminder(r['id'],
                       (datetime.now() + timedelta(hours=1)).isoformat(timespec='seconds'))
    assert not any(x['id'] == r['id'] for x in db.pending_reminders(user['id']))


# ── HTTP route ─────────────────────────────────────────────────────────────

def _login(client, user, password='pw'):
    return client.post('/api/auth/login',
                       json={'login': user['name'], 'password': password})


def test_snooze_route_preset(client, make_user):
    user = make_user('Clay')
    r = db.create_reminder(user['id'], 'milk', _past())
    db.mark_reminder_fired(r['id'])
    _login(client, user)
    resp = client.post(f"/api/reminders/{r['id']}/snooze", json={'preset': '1h'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['fired'] == 0
    fire_at = datetime.fromisoformat(body['fire_at'])
    assert datetime.now() < fire_at <= datetime.now() + timedelta(hours=1, minutes=1)


def test_snooze_route_minutes(client, make_user):
    user = make_user('Clay')
    r = db.create_reminder(user['id'], 'milk', _past())
    _login(client, user)
    resp = client.post(f"/api/reminders/{r['id']}/snooze", json={'minutes': 30})
    assert resp.status_code == 200
    fire_at = datetime.fromisoformat(resp.get_json()['fire_at'])
    assert fire_at > datetime.now() + timedelta(minutes=25)


def test_snooze_route_rejects_bad_input(client, make_user):
    user = make_user('Clay')
    r = db.create_reminder(user['id'], 'milk', _past())
    _login(client, user)
    assert client.post(f"/api/reminders/{r['id']}/snooze",
                       json={'minutes': 0}).status_code == 400
    assert client.post(f"/api/reminders/{r['id']}/snooze",
                       json={'preset': 'whenever'}).status_code == 400


def test_snooze_route_other_users_reminder_404(client, make_user):
    owner = make_user('Owner')
    other = make_user('Other')
    r = db.create_reminder(other['id'], 'theirs', _past())
    _login(client, owner)
    assert client.post(f"/api/reminders/{r['id']}/snooze",
                       json={'preset': '1h'}).status_code == 404
    # Untouched.
    assert db.get_reminder(r['id'])['fire_at'] == r['fire_at']


# ── MCP tool ───────────────────────────────────────────────────────────────

def test_mcp_snooze_reminder(make_user):
    user = make_user('Clay')
    r = db.create_reminder(user['id'], 'standup', _past())
    db.mark_reminder_fired(r['id'])
    out = mcp_server._tool_snooze_reminder(user, {'reminder_id': r['id'],
                                                  'when': 'in 3 hours'})
    assert 'Snoozed' in out
    row = db.get_reminder(r['id'])
    assert row['fired'] == 0
    assert datetime.fromisoformat(row['fire_at']) > datetime.now()


def test_mcp_snooze_rejects_past(make_user):
    user = make_user('Clay')
    r = db.create_reminder(user['id'], 'standup', _past())
    try:
        mcp_server._tool_snooze_reminder(user, {'reminder_id': r['id'],
                                                'when': 'yesterday'})
        assert False, 'expected ToolError'
    except mcp_server.ToolError:
        pass


def test_mcp_snooze_unknown_reminder(make_user):
    user = make_user('Clay')
    try:
        mcp_server._tool_snooze_reminder(user, {'reminder_id': 'nope',
                                                'when': 'in 1 hour'})
        assert False, 'expected ToolError'
    except mcp_server.ToolError:
        pass
