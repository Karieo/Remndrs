"""Tier 1 — note visibility rule.

The invariant used everywhere: a user sees their own ``feed='private'`` rows
plus anyone's ``feed='shared'`` rows. It is enforced both in the SQL of
``database.list_notes`` and in ``app._can_see`` (used by the single-note,
attachment and reply routes). A bug here leaks private notes between users.
"""

import database as db


def _ids(notes):
    return {n['id'] for n in notes}


# ── database.list_notes ────────────────────────────────────────────────────

def test_user_sees_own_private(make_user, make_note):
    alice = make_user('Alice')
    n = make_note(alice, content='alice private', feed='private')
    assert n['id'] in _ids(db.list_notes(alice['id']))


def test_user_does_not_see_others_private(make_user, make_note):
    alice = make_user('Alice')
    bob = make_user('Bob')
    secret = make_note(bob, content='bob private', feed='private')
    assert secret['id'] not in _ids(db.list_notes(alice['id']))


def test_shared_notes_visible_to_everyone(make_user, make_note):
    alice = make_user('Alice')
    bob = make_user('Bob')
    shared = make_note(bob, content='bob shared', feed='shared')
    assert shared['id'] in _ids(db.list_notes(alice['id']))
    assert shared['id'] in _ids(db.list_notes(bob['id']))


def test_list_notes_full_matrix(make_user, make_note):
    alice = make_user('Alice')
    bob = make_user('Bob')
    a_priv = make_note(alice, feed='private')
    a_shar = make_note(alice, feed='shared')
    b_priv = make_note(bob, feed='private')
    b_shar = make_note(bob, feed='shared')

    seen_by_alice = _ids(db.list_notes(alice['id']))
    assert a_priv['id'] in seen_by_alice
    assert a_shar['id'] in seen_by_alice
    assert b_shar['id'] in seen_by_alice
    assert b_priv['id'] not in seen_by_alice   # the one row she must not see


def test_archived_excluded_by_default_included_in_archived_view(make_user, make_note):
    alice = make_user('Alice')
    n = make_note(alice, feed='private')
    db.update_note(n['id'], archived=True)
    assert n['id'] not in _ids(db.list_notes(alice['id']))
    assert n['id'] in _ids(db.list_notes(alice['id'], archived=True))


def test_feed_filter_narrows_results(make_user, make_note):
    alice = make_user('Alice')
    priv = make_note(alice, feed='private')
    shar = make_note(alice, feed='shared')
    only_private = _ids(db.list_notes(alice['id'], feed='private'))
    assert priv['id'] in only_private
    assert shar['id'] not in only_private


# ── app._can_see ───────────────────────────────────────────────────────────

def test_can_see_matches_list_notes_rule():
    import app as appmod
    owner_priv = {'user_id': 'u1', 'feed': 'private'}
    owner_shared = {'user_id': 'u1', 'feed': 'shared'}
    assert appmod._can_see(owner_priv, 'u1') is True
    assert appmod._can_see(owner_priv, 'u2') is False    # other's private
    assert appmod._can_see(owner_shared, 'u2') is True   # anyone's shared
    assert appmod._can_see(None, 'u1') is None or appmod._can_see(None, 'u1') is False


# ── per-user retrieval helpers (SMS/MCP) stay scoped to the owner ──────────

def test_recent_and_search_are_owner_scoped(make_user, make_note):
    alice = make_user('Alice')
    bob = make_user('Bob')
    make_note(bob, content='bob shared note', feed='shared')
    # recent_notes / search are single-user views — they must NOT pull in
    # another user's shared notes (unlike the web feed).
    assert db.recent_notes(alice['id']) == []
    assert db.search_user_notes(alice['id'], 'shared') == []
