"""AI note summarization: self-disabling without a key, returns the model text
with a mocked OpenAI client, and the /api/ai/summarize route."""

import sys
import types

import ai


def _install_fake_openai(monkeypatch, reply):
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
    assert ai.summarize('a long note about things') == ''


def test_empty_content_returns_empty(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    assert ai.summarize('   ') == ''


def test_returns_model_summary(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    _install_fake_openai(monkeypatch, '  Buy ingredients and cook dinner.  ')
    assert ai.summarize('long recipe...') == 'Buy ingredients and cook dinner.'


def test_error_returns_empty(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    fake = types.ModuleType('openai')

    class _Boom:
        def __init__(self, **kw): raise RuntimeError('down')
    fake.OpenAI = _Boom
    monkeypatch.setitem(sys.modules, 'openai', fake)
    assert ai.summarize('x') == ''


def test_route_reports_configured(client, make_user, monkeypatch):
    make_user('Clay')
    client.post('/api/auth/login', json={'login': 'Clay', 'password': 'pw'})
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    resp = client.post('/api/ai/summarize', json={'content': 'hello'})
    assert resp.status_code == 200
    assert resp.get_json() == {'configured': False, 'summary': ''}
