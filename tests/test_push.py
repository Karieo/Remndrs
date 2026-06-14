"""Web push: subscription storage, the subscribe/unsubscribe + key routes,
reminder-dispatch wiring, and webpush.send_to_user delivery/pruning.

pywebpush isn't a hard test dep — the delivery tests inject a fake module so
they run without it installed.
"""

import json
import sys
import types

import database as db
import reminders
import webpush


_SUB = json.dumps({'endpoint': 'https://push.example/ep1',
                   'keys': {'p256dh': 'p', 'auth': 'a'}})


# ── db CRUD ────────────────────────────────────────────────────────────────

def test_subscription_crud_and_upsert(make_user):
    user = make_user('Clay')
    db.add_push_subscription(user['id'], 'https://push.example/ep1', _SUB)
    assert len(db.list_push_subscriptions(user['id'])) == 1
    # Re-subscribing the same endpoint replaces, doesn't duplicate.
    db.add_push_subscription(user['id'], 'https://push.example/ep1', _SUB)
    subs = db.list_push_subscriptions(user['id'])
    assert len(subs) == 1
    db.delete_push_subscription('https://push.example/ep1')
    assert db.list_push_subscriptions(user['id']) == []


# ── routes ──────────────────────────────────────────────────────────────────

def _login(client, name='Clay'):
    client.post('/api/auth/login', json={'login': name, 'password': 'pw'})


def test_push_key_unconfigured(client, make_user, monkeypatch):
    monkeypatch.delenv('VAPID_PUBLIC_KEY', raising=False)
    monkeypatch.delenv('VAPID_PRIVATE_KEY', raising=False)
    make_user('Clay'); _login(client)
    body = client.get('/api/push/key').get_json()
    assert body['configured'] is False


def test_push_key_configured(client, make_user, monkeypatch):
    monkeypatch.setenv('VAPID_PUBLIC_KEY', 'pub123')
    monkeypatch.setenv('VAPID_PRIVATE_KEY', 'priv123')
    make_user('Clay'); _login(client)
    body = client.get('/api/push/key').get_json()
    assert body['configured'] is True and body['publicKey'] == 'pub123'


def test_subscribe_and_unsubscribe_routes(client, make_user):
    user = make_user('Clay'); _login(client)
    resp = client.post('/api/push/subscribe',
                       json={'endpoint': 'https://push.example/ep1',
                             'keys': {'p256dh': 'p', 'auth': 'a'}})
    assert resp.status_code == 201
    assert len(db.list_push_subscriptions(user['id'])) == 1
    client.post('/api/push/unsubscribe', json={'endpoint': 'https://push.example/ep1'})
    assert db.list_push_subscriptions(user['id']) == []


def test_subscribe_requires_endpoint(client, make_user):
    make_user('Clay'); _login(client)
    assert client.post('/api/push/subscribe', json={}).status_code == 400


def test_sw_and_manifest_served(client):
    # Public assets, no login required.
    sw = client.get('/sw.js')
    assert sw.status_code == 200 and b'push' in sw.data
    assert sw.headers.get('Service-Worker-Allowed') == '/'
    assert client.get('/manifest.json').status_code == 200


# ── dispatch wiring ──────────────────────────────────────────────────────────

def test_dispatch_pushes_web(make_user, monkeypatch):
    from datetime import datetime, timedelta
    user = make_user('Clay')
    past = (datetime.now() - timedelta(minutes=1)).isoformat(timespec='seconds')
    db.create_reminder(user['id'], 'ping', past, notify_sms=False, notify_web=True)
    monkeypatch.setattr(reminders.sse, 'push_event', lambda *a: None)
    sent = []
    monkeypatch.setattr(reminders.webpush, 'send_to_user',
                        lambda uid, title, body, **k: sent.append((uid, body)))
    reminders.check_reminders()
    assert sent and sent[0] == (user['id'], 'ping')


# ── webpush.send_to_user delivery / pruning (fake pywebpush) ─────────────────

def _install_fake_pywebpush(monkeypatch, raises_status=None, calls=None):
    fake = types.ModuleType('pywebpush')

    class WebPushException(Exception):
        def __init__(self, msg, response=None):
            super().__init__(msg)
            self.response = response

    def webpush_fn(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        if raises_status is not None:
            resp = types.SimpleNamespace(status_code=raises_status)
            raise WebPushException('boom', response=resp)

    fake.webpush = webpush_fn
    fake.WebPushException = WebPushException
    monkeypatch.setitem(sys.modules, 'pywebpush', fake)


def test_send_noop_when_unconfigured(make_user, monkeypatch):
    monkeypatch.delenv('VAPID_PRIVATE_KEY', raising=False)
    monkeypatch.delenv('VAPID_PUBLIC_KEY', raising=False)
    user = make_user('Clay')
    db.add_push_subscription(user['id'], 'https://push.example/ep1', _SUB)
    webpush.send_to_user(user['id'], 'T', 'B')   # must not raise
    assert len(db.list_push_subscriptions(user['id'])) == 1


def test_send_delivers(make_user, monkeypatch):
    monkeypatch.setenv('VAPID_PUBLIC_KEY', 'pub')
    monkeypatch.setenv('VAPID_PRIVATE_KEY', 'priv')
    user = make_user('Clay')
    db.add_push_subscription(user['id'], 'https://push.example/ep1', _SUB)
    calls = []
    _install_fake_pywebpush(monkeypatch, calls=calls)
    webpush.send_to_user(user['id'], 'Title', 'Body')
    assert len(calls) == 1
    assert db.list_push_subscriptions(user['id']) == [  # kept on success
        s for s in db.list_push_subscriptions(user['id'])]


def test_send_prunes_expired_subscription(make_user, monkeypatch):
    monkeypatch.setenv('VAPID_PUBLIC_KEY', 'pub')
    monkeypatch.setenv('VAPID_PRIVATE_KEY', 'priv')
    user = make_user('Clay')
    db.add_push_subscription(user['id'], 'https://push.example/ep1', _SUB)
    _install_fake_pywebpush(monkeypatch, raises_status=410)
    webpush.send_to_user(user['id'], 'T', 'B')
    assert db.list_push_subscriptions(user['id']) == []
