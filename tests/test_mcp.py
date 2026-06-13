"""Tier 2 — MCP JSON-RPC dispatch and tool handlers (mcp_server.py).

Protocol-level behaviour (initialize/ping/tools, notifications, error codes,
batching) plus the tool handlers that read/write notes.
"""

import database as db
import mcp_server as mcp


# ── _limit clamping (pure) ─────────────────────────────────────────────────

def test_limit_default():
    assert mcp._limit({}) == 5


def test_limit_clamps_to_bounds():
    assert mcp._limit({'limit': 0}) == 1
    assert mcp._limit({'limit': 999}) == mcp.MAX_RESULTS
    assert mcp._limit({'limit': 7}) == 7


def test_limit_bad_value_falls_back():
    assert mcp._limit({'limit': 'lots'}) == 5
    assert mcp._limit({'limit': None}) == 5


# ── _dispatch protocol handling ────────────────────────────────────────────

def _user():
    return {'id': 'u1', 'name': 'Clay'}


def test_dispatch_rejects_non_jsonrpc():
    err = mcp._dispatch(_user(), {'method': 'ping', 'id': 1})
    assert err['error']['code'] == -32600


def test_dispatch_initialize_echoes_supported_version():
    resp = mcp._dispatch(_user(), {
        'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {'protocolVersion': '2025-06-18'}})
    assert resp['result']['protocolVersion'] == '2025-06-18'
    assert resp['result']['serverInfo']['name'] == 'Remndrs'


def test_dispatch_ping():
    resp = mcp._dispatch(_user(), {'jsonrpc': '2.0', 'id': 2, 'method': 'ping'})
    assert resp == {'jsonrpc': '2.0', 'id': 2, 'result': {}}


def test_dispatch_tools_list():
    resp = mcp._dispatch(_user(), {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})
    names = {t['name'] for t in resp['result']['tools']}
    assert {'add_note', 'add_reminder', 'search_notes'} <= names


def test_dispatch_notification_returns_none():
    # No 'id' → a notification; nothing to answer.
    assert mcp._dispatch(_user(), {'jsonrpc': '2.0', 'method': 'initialized'}) is None


def test_dispatch_unknown_method():
    resp = mcp._dispatch(_user(), {'jsonrpc': '2.0', 'id': 4, 'method': 'nope'})
    assert resp['error']['code'] == -32601


# ── handle (batch + notification status codes) ─────────────────────────────

def test_handle_parse_error_on_none():
    body, status = mcp.handle(_user(), None)
    assert body['error']['code'] == -32700
    assert status == 200


def test_handle_notification_only_batch_returns_202():
    body, status = mcp.handle(_user(), [{'jsonrpc': '2.0', 'method': 'initialized'}])
    assert body is None
    assert status == 202


def test_handle_batch_returns_responses():
    body, status = mcp.handle(_user(), [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}])
    assert status == 200
    assert {r['id'] for r in body} == {1, 2}


# ── tool handlers (DB-backed) ──────────────────────────────────────────────

def test_tool_add_note_creates_note_with_dedup_tags(make_user):
    user = make_user('Clay')
    out = mcp._tool_add_note(user, {'content': 'plan #work', 'tags': ['work', 'BIG']})
    assert 'aved' in out or 'note' in out.lower()
    note = db.recent_notes(user['id'])[0]
    names = [t['name'] for t in note['tags']]
    assert names.count('WORK') == 1   # #work + 'work' deduped
    assert 'BIG' in names
    assert note['source'] == 'claude'


def test_tool_add_note_shared_flag_routes_feed(make_user):
    user = make_user('Clay')
    mcp._tool_add_note(user, {'content': 'dinner', 'shared': True})
    assert db.list_notes(user['id'])[0]['feed'] == 'shared'


def test_tool_search_requires_query(make_user):
    user = make_user('Clay')
    try:
        mcp._tool_search_notes(user, {'query': '   '})
        assert False, 'expected ToolError'
    except mcp.ToolError:
        pass


def test_tool_search_finds_note(make_user, make_note):
    user = make_user('Clay')
    make_note(user, content='buy concert tickets')
    out = mcp._tool_search_notes(user, {'query': 'concert'})
    assert 'concert' in out


def test_tool_add_reminder_rejects_past_time(make_user):
    user = make_user('Clay')
    try:
        mcp._tool_add_reminder(user, {'when': '2000-01-01T00:00', 'message': 'old'})
        assert False, 'expected ToolError'
    except mcp.ToolError:
        pass


def test_tool_add_reminder_accepts_future_iso(make_user):
    user = make_user('Clay')
    out = mcp._tool_add_reminder(user, {'when': '2099-01-01T09:00', 'message': 'party'})
    assert 'party' in out
    pending = db.list_reminders(user['id'])  # unfired reminders for this user
    assert pending and pending[0]['message'] == 'party'
