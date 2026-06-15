"""AI tag suggestions: self-disabling without a key, parsing/normalization with
a mocked OpenAI client, and the /api/ai/suggest-tags route."""

import sys
import types

import ai


def _install_fake_openai(monkeypatch, reply):
    """Inject a fake `openai` module whose chat completion returns `reply`."""
    fake = types.ModuleType('openai')

    class _Msg:
        def __init__(self, c): self.message = types.SimpleNamespace(content=c)

    class _Client:
        def __init__(self, **kw):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=lambda **kw: types.SimpleNamespace(choices=[_Msg(reply)])))

    fake.OpenAI = _Client
    monkeypatch.setitem(sys.modules, 'openai', fake)


def test_no_key_returns_empty(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    assert ai.suggest_tags('some content') == []
    assert ai.configured() is False


def test_suggests_normalized_tags(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    _install_fake_openai(monkeypatch, '["Travel", "#Italy", "summer trip"]')
    out = ai.suggest_tags('Planning a trip to Rome this summer')
    # uppercased, '#'/space stripped
    assert out == ['TRAVEL', 'ITALY', 'SUMMERTRIP']


def test_excludes_existing_and_dedupes(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    _install_fake_openai(monkeypatch, '["WORK", "work", "ERRANDS"]')
    out = ai.suggest_tags('content', existing=['WORK'])
    assert out == ['ERRANDS']


def test_bad_reply_falls_back_to_split(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    _install_fake_openai(monkeypatch, 'home, garden, weekend')
    assert ai.suggest_tags('x') == ['HOME', 'GARDEN', 'WEEKEND']


def test_error_returns_empty(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    fake = types.ModuleType('openai')

    class _Boom:
        def __init__(self, **kw): raise RuntimeError('api down')
    fake.OpenAI = _Boom
    monkeypatch.setitem(sys.modules, 'openai', fake)
    assert ai.suggest_tags('x') == []


def test_route_reports_configured(client, make_user, monkeypatch):
    make_user('Clay')
    client.post('/api/auth/login', json={'login': 'Clay', 'password': 'pw'})
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    resp = client.post('/api/ai/suggest-tags', json={'content': 'hi'})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body == {'configured': False, 'tags': []}
