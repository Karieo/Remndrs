"""Daily digest: prefs storage, content building, the once-a-day scheduler
sweep (with dedupe), and the /api/users/me digest_hour surface.
"""

from datetime import date, datetime, timedelta

import database as db
import digest


def _recent_iso():
    return (datetime.now() - timedelta(hours=1)).isoformat(timespec='seconds')


# ── prefs + content queries ─────────────────────────────────────────────────

def test_set_and_query_digest_hour(make_user):
    user = make_user('Clay')
    assert db.get_user(user['id'])['digest_hour'] is None
    db.set_user_digest_hour(user['id'], 8)
    assert db.get_user(user['id'])['digest_hour'] == 8
    assert [u['id'] for u in db.users_for_digest_hour(8)] == [user['id']]
    assert db.users_for_digest_hour(9) == []


def test_notes_since_respects_visibility(make_user, make_note):
    clay = make_user('Clay')
    mia = make_user('Mia')
    make_note(clay, content='clay private')
    make_note(mia, content='mia private')          # not visible to clay
    make_note(mia, content='mia shared', feed='shared')
    contents = [n['content'] for n in db.notes_since(clay['id'], '2000-01-01T00:00:00')]
    assert 'clay private' in contents
    assert 'mia shared' in contents
    assert 'mia private' not in contents


# ── build_digest ─────────────────────────────────────────────────────────────

def test_build_digest_none_when_empty(make_user):
    user = make_user('Clay')
    assert digest.build_digest(user) is None


def test_build_digest_includes_notes_and_reminders(make_user, make_note):
    user = make_user('Clay')
    make_note(user, content='Buy milk\nand eggs')
    soon = (datetime.now() + timedelta(hours=2)).isoformat(timespec='seconds')
    db.create_reminder(user['id'], 'call mom', soon)
    built = digest.build_digest(user)
    assert built is not None
    _subject, body = built
    assert 'call mom' in body
    assert 'Buy milk' in body            # first line only
    assert 'and eggs' not in body


# ── scheduler sweep ──────────────────────────────────────────────────────────

def test_send_digests_marks_sent_and_dedupes(make_user, make_note, monkeypatch):
    user = make_user('Clay')
    db.set_user_digest_hour(user['id'], 7)
    make_note(user, content='something today')
    sent = []
    monkeypatch.setattr(digest, '_deliver', lambda u, s, b: sent.append(u['id']) or True)

    digest.send_digests_for_hour(7)
    assert sent == [user['id']]
    assert db.get_user(user['id'])['digest_last_sent'] == date.today().isoformat()

    # Second sweep the same day is a no-op (already sent).
    digest.send_digests_for_hour(7)
    assert sent == [user['id']]


def test_send_digests_skips_other_hours(make_user, make_note, monkeypatch):
    user = make_user('Clay')
    db.set_user_digest_hour(user['id'], 7)
    make_note(user, content='x')
    sent = []
    monkeypatch.setattr(digest, '_deliver', lambda u, s, b: sent.append(u['id']) or True)
    digest.send_digests_for_hour(8)      # wrong hour
    assert sent == []


# ── route ────────────────────────────────────────────────────────────────────

def test_users_me_digest_hour_roundtrip(client, make_user):
    user = make_user('Clay')
    client.post('/api/auth/login', json={'login': 'Clay', 'password': 'pw'})
    assert client.get('/api/users/me').get_json()['digest_hour'] is None
    client.patch('/api/users/me', json={'digest_hour': 9})
    assert client.get('/api/users/me').get_json()['digest_hour'] == 9
    client.patch('/api/users/me', json={'digest_hour': None})
    assert client.get('/api/users/me').get_json()['digest_hour'] is None
    assert client.patch('/api/users/me', json={'digest_hour': 99}).status_code == 400
