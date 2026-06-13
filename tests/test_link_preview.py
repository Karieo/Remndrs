"""Link previews must not surface CDN/bot block pages (e.g. a 403 "Access
Denied" from Akamai) as note cards, and must self-heal any cached before the
fix landed.
"""

import pytest
import requests

import app as appmod
import database as db


class _FakeResp:
    def __init__(self, text='', status_code=200):
        self.text = text
        self.status_code = status_code
        self.ok = status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(str(self.status_code))


@pytest.fixture
def login(client):
    def _login(user):
        with client.session_transaction() as sess:
            sess['user_id'] = user['id']
    return _login


def _fake_get(monkeypatch, resp):
    monkeypatch.setattr(appmod.http, 'get', lambda *a, **k: resp)


def test_preview_rejects_403_block_page(client, login, make_user, monkeypatch):
    login(make_user('Clay'))
    _fake_get(monkeypatch, _FakeResp('<title>Access Denied</title>', 403))
    body = client.get('/api/preview?url=https://www.jared.com/x').get_json()
    assert body.get('error')                                  # no title => no card
    assert db.get_link_preview('https://www.jared.com/x') is None  # not cached


def test_preview_rejects_200_block_title(client, login, make_user, monkeypatch):
    login(make_user('Clay'))
    _fake_get(monkeypatch, _FakeResp('<title>Just a moment...</title>', 200))
    body = client.get('/api/preview?url=https://ex.com/y').get_json()
    assert body.get('error')
    assert db.get_link_preview('https://ex.com/y') is None


def test_preview_caches_real_page(client, login, make_user, monkeypatch):
    login(make_user('Clay'))
    _fake_get(monkeypatch, _FakeResp('<title>Real Article</title>'))
    body = client.get('/api/preview?url=https://ex.com/good').get_json()
    assert body['title'] == 'Real Article'
    assert db.get_link_preview('https://ex.com/good')['title'] == 'Real Article'


def test_preview_self_heals_cached_block(client, login, make_user, monkeypatch):
    login(make_user('Clay'))
    db.save_link_preview('https://ex.com/z', 'Access Denied',
                         None, None, None, None)
    _fake_get(monkeypatch, _FakeResp('<title>Recovered</title>'))
    body = client.get('/api/preview?url=https://ex.com/z').get_json()
    assert body['title'] == 'Recovered'  # poisoned row dropped, real page served
