"""Tier 1 — authentication boundary (app.require_login, PUBLIC_PATHS, bearer).

These guard the line between an anonymous request and an authenticated one. A
regression here either locks everyone out or — worse — lets anonymous requests
reach protected routes.
"""

import hashlib

import pytest


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ── PUBLIC_PATHS allowlist ─────────────────────────────────────────────────

def test_public_paths_reachable_without_auth(client):
    # Login page and version endpoint are explicitly public.
    assert client.get('/login').status_code == 200
    assert client.get('/api/version').status_code == 200


def test_protected_api_route_requires_auth(client):
    resp = client.get('/api/notes')
    assert resp.status_code == 401
    assert resp.get_json()['error'] == 'Unauthorized'


def test_protected_page_redirects_to_login(client):
    resp = client.get('/')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/login')


@pytest.mark.parametrize('path', [
    '/api/notes',          # protected API
    '/api/settings',       # owner-only API
    '/api/tags',           # protected API
])
def test_near_miss_paths_are_not_public(client, path):
    # Prefix matching in require_login must not accidentally open these.
    assert client.get(path).status_code in (401, 404)


def test_webhooks_prefix_does_not_leak_to_lookalike(client):
    # '/webhooks/' is public, but a lookalike that merely starts differently
    # must still be gated. '/webhooksX' does NOT start with '/webhooks/'.
    resp = client.get('/webhooksX')
    assert resp.status_code in (302, 401, 404)
    # And a real webhook path is reachable (auth-wise) — it won't 401/redirect
    # for being unauthenticated, though it may 403 on a bad signature or 404.
    resp = client.post('/webhooks/sms')
    assert resp.status_code != 401


# ── Session login flow ─────────────────────────────────────────────────────

def test_login_success_sets_session_and_grants_access(client, make_user):
    make_user('Clay', password='secret', role='owner')
    resp = client.post('/api/auth/login', json={'login': 'Clay', 'password': 'secret'})
    assert resp.status_code == 200
    # Cookie-backed session now grants access to a protected route.
    assert client.get('/api/notes').status_code == 200


def test_login_wrong_password_rejected(client, make_user):
    make_user('Clay', password='secret')
    resp = client.post('/api/auth/login', json={'login': 'Clay', 'password': 'nope'})
    assert resp.status_code == 401
    assert client.get('/api/notes').status_code == 401


def test_login_is_case_insensitive_on_name(client, make_user):
    make_user('Clay', password='secret')
    resp = client.post('/api/auth/login', json={'login': 'clay', 'password': 'secret'})
    assert resp.status_code == 200


# ── Bearer-token auth (iOS / MCP clients) ──────────────────────────────────

def test_bearer_token_grants_access(client, make_user):
    import database as db
    user = make_user('Mobile')
    db.create_api_token(user['id'], _token_hash('tok-abc'), device_name='iPhone')
    resp = client.get('/api/notes', headers={'Authorization': 'Bearer tok-abc'})
    assert resp.status_code == 200


def test_bearer_token_request_sets_no_cookie(client, make_user):
    """Token clients are request-scoped: the server must not hand them a
    session cookie (the `session.modified = False` invariant)."""
    import database as db
    user = make_user('Mobile')
    db.create_api_token(user['id'], _token_hash('tok-xyz'))
    resp = client.get('/api/notes', headers={'Authorization': 'Bearer tok-xyz'})
    assert resp.status_code == 200
    assert 'Set-Cookie' not in resp.headers


def test_unknown_bearer_token_rejected(client, make_user):
    make_user('Mobile')
    resp = client.get('/api/notes', headers={'Authorization': 'Bearer bogus'})
    assert resp.status_code == 401


def test_malformed_authorization_header_rejected(client, make_user):
    make_user('Mobile')
    for header in ('tok-abc', 'Basic abc', 'Bearer', ''):
        resp = client.get('/api/notes', headers={'Authorization': header})
        assert resp.status_code == 401, header


# ── Failed-login throttle ──────────────────────────────────────────────────

def test_repeated_failures_throttle_the_ip(client, make_user):
    import app as appmod
    make_user('Clay', password='secret')
    # _THROTTLE_MAX failures should trip the 429.
    for _ in range(appmod._THROTTLE_MAX):
        client.post('/api/auth/login', json={'login': 'Clay', 'password': 'x'})
    resp = client.post('/api/auth/login', json={'login': 'Clay', 'password': 'secret'})
    assert resp.status_code == 429
