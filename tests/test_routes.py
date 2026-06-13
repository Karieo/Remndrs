"""Tier 3 — app.py route bodies via the Flask test client.

Note persistence invariant (DB row + .md file written together, feed-change
moves the file), person-to-person share + replies, send-anywhere, and the
owner-gated settings endpoints.
"""

import os

import pytest

import database as db


@pytest.fixture
def login(client):
    """Put a user's id in the session so protected routes see them."""
    def _login(user):
        with client.session_transaction() as sess:
            sess['user_id'] = user['id']
    return _login


@pytest.fixture(autouse=True)
def notes_in_tmp(monkeypatch, tmp_path):
    """Isolate the .md mirror to a per-test dir."""
    monkeypatch.setenv('NOTES_FOLDER', str(tmp_path / 'notes'))
    return tmp_path / 'notes'


# ── Note creation persists DB row + .md file together ──────────────────────

def test_create_note_writes_db_row_and_file(client, login, make_user, notes_in_tmp):
    user = make_user('Clay')
    login(user)
    resp = client.post('/api/notes', json={'content': 'first note'})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['filename']                      # filename recorded on the row
    path = notes_in_tmp / 'Clay' / body['filename']
    assert path.exists()
    assert 'first note' in path.read_text()


def test_changing_feed_moves_the_file(client, login, make_user, notes_in_tmp):
    user = make_user('Clay')
    login(user)
    note = client.post('/api/notes', json={'content': 'movable'}).get_json()
    old = notes_in_tmp / 'Clay' / note['filename']
    assert old.exists()

    updated = client.patch(f"/api/notes/{note['id']}", json={'feed': 'shared'}).get_json()
    assert updated['feed'] == 'shared'
    assert not old.exists()                       # gone from the private folder
    assert (notes_in_tmp / 'Shared' / updated['filename']).exists()


def test_update_note_others_private_is_not_found(client, login, make_user):
    alice = make_user('Alice')
    bob = make_user('Bob')
    note = db.create_note(bob['id'], content='bob secret', feed='private')
    login(alice)
    resp = client.patch(f"/api/notes/{note['id']}", json={'content': 'hacked'})
    assert resp.status_code == 404


# ── Share ──────────────────────────────────────────────────────────────────

def test_share_moves_note_to_shared_with_attribution(client, login, make_user, notes_in_tmp):
    alice = make_user('Alice')
    bob = make_user('Bob')
    note = db.create_note(alice['id'], content='dinner plan', feed='private')
    login(alice)
    resp = client.post(f"/api/notes/{note['id']}/share",
                       json={'recipient_id': bob['id'], 'message': 'fyi'})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['feed'] == 'shared'
    assert body['share']['sender_name'] == 'Alice'
    assert body['share']['recipient_name'] == 'Bob'
    assert (notes_in_tmp / 'Shared' / body['filename']).exists()


def test_share_with_self_rejected(client, login, make_user):
    alice = make_user('Alice')
    note = db.create_note(alice['id'], content='x')
    login(alice)
    resp = client.post(f"/api/notes/{note['id']}/share", json={'recipient_id': alice['id']})
    assert resp.status_code == 400


def test_share_unknown_recipient_404(client, login, make_user):
    alice = make_user('Alice')
    note = db.create_note(alice['id'], content='x')
    login(alice)
    resp = client.post(f"/api/notes/{note['id']}/share", json={'recipient_id': 'ghost'})
    assert resp.status_code == 404


# ── Replies ────────────────────────────────────────────────────────────────

def test_reply_to_shared_note_appends_to_markdown(client, login, make_user, notes_in_tmp):
    alice = make_user('Alice')
    note = db.create_note(alice['id'], content='group note', feed='shared')
    login(alice)
    resp = client.post(f"/api/notes/{note['id']}/replies", json={'text': 'sounds good'})
    assert resp.status_code == 201
    assert resp.get_json()['text'] == 'sounds good'
    md = (notes_in_tmp / 'Shared' / db.get_note(note['id'])['filename']).read_text()
    assert '## Replies' in md
    assert 'sounds good' in md


def test_reply_to_private_note_rejected(client, login, make_user):
    alice = make_user('Alice')
    note = db.create_note(alice['id'], content='solo', feed='private')
    login(alice)
    resp = client.post(f"/api/notes/{note['id']}/replies", json={'text': 'hi'})
    assert resp.status_code == 400


def test_reply_requires_text(client, login, make_user):
    alice = make_user('Alice')
    note = db.create_note(alice['id'], content='x', feed='shared')
    login(alice)
    resp = client.post(f"/api/notes/{note['id']}/replies", json={'text': '   '})
    assert resp.status_code == 400


# ── Send anywhere ──────────────────────────────────────────────────────────

def test_send_unconfigured_channels_return_503(client, login, make_user, monkeypatch):
    monkeypatch.delenv('TWILIO_ACCOUNT_SID', raising=False)
    monkeypatch.delenv('TWILIO_AUTH_TOKEN', raising=False)
    monkeypatch.delenv('MAILGUN_API_KEY', raising=False)
    monkeypatch.delenv('MAILGUN_INBOUND_ADDRESS', raising=False)
    alice = make_user('Alice')
    note = db.create_note(alice['id'], content='x')
    login(alice)
    assert client.post(f"/api/notes/{note['id']}/send",
                       json={'channel': 'sms', 'to': '+1555'}).status_code == 503
    assert client.post(f"/api/notes/{note['id']}/send",
                       json={'channel': 'email', 'to': 'a@b.com'}).status_code == 503


def test_send_invalid_channel_400(client, login, make_user):
    alice = make_user('Alice')
    note = db.create_note(alice['id'], content='x')
    login(alice)
    resp = client.post(f"/api/notes/{note['id']}/send", json={'channel': 'carrier-pigeon'})
    assert resp.status_code == 400


def test_send_sms_invokes_twilio_when_configured(client, login, make_user, monkeypatch):
    monkeypatch.setenv('TWILIO_ACCOUNT_SID', 'AC123')
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', 'tok')
    sent = []
    import sms
    monkeypatch.setattr(sms, 'send_sms', lambda u, to, body: sent.append((to, body)))
    alice = make_user('Alice')
    note = db.create_note(alice['id'], content='ping you')
    login(alice)
    resp = client.post(f"/api/notes/{note['id']}/send",
                       json={'channel': 'sms', 'to': '+15551234567'})
    assert resp.status_code == 200
    assert sent == [('+15551234567', 'ping you')]


# ── Settings (owner only) ──────────────────────────────────────────────────

def test_settings_get_requires_owner(client, login, make_user):
    member = make_user('Member', role='member')
    login(member)
    assert client.get('/api/settings').status_code == 403


def test_settings_get_ok_for_owner(client, login, make_user):
    owner = make_user('Owner', role='owner')
    login(owner)
    resp = client.get('/api/settings')
    assert resp.status_code == 200
    assert 'status' in resp.get_json()


def test_settings_patch_requires_owner(client, login, make_user):
    member = make_user('Member', role='member')
    login(member)
    resp = client.patch('/api/settings', json={'TWILIO_ACCOUNT_SID': 'AC9'})
    assert resp.status_code == 403


def test_settings_patch_writes_env_and_live(client, login, make_user, monkeypatch, tmp_path):
    import app as appmod
    env_file = tmp_path / '.env'
    monkeypatch.setattr(appmod, 'ENV_PATH', str(env_file))
    # _write_env mutates os.environ directly; pre-record the key so monkeypatch
    # restores (deletes) it on teardown and the value can't leak to other tests.
    monkeypatch.setenv('TWILIO_ACCOUNT_SID', '')
    owner = make_user('Owner', role='owner')
    login(owner)
    resp = client.patch('/api/settings', json={'TWILIO_ACCOUNT_SID': 'AC777',
                                               'NOT_A_KEY': 'ignored'})
    assert resp.status_code == 200
    assert resp.get_json()['updated'] == ['TWILIO_ACCOUNT_SID']
    assert os.environ['TWILIO_ACCOUNT_SID'] == 'AC777'   # applied live
    assert 'TWILIO_ACCOUNT_SID=AC777' in env_file.read_text()
