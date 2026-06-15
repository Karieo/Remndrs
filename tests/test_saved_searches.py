"""Saved searches: db CRUD (with tags JSON round-trip) + the
/api/saved-searches routes."""

import database as db


def _login(client, name='Clay'):
    client.post('/api/auth/login', json={'login': name, 'password': 'pw'})


def test_saved_search_crud_roundtrips_tags(make_user):
    user = make_user('Clay')
    s = db.create_saved_search(user['id'], 'Work', feed='shared', channel='sms',
                               tags=['WORK', 'URGENT'], search='invoice')
    assert s['tags'] == ['WORK', 'URGENT']
    assert s['feed'] == 'shared' and s['channel'] == 'sms' and s['search'] == 'invoice'
    got = db.get_saved_search(s['id'])
    assert got['tags'] == ['WORK', 'URGENT']
    db.delete_saved_search(s['id'])
    assert db.list_saved_searches(user['id']) == []


def test_saved_searches_per_user(make_user):
    clay = make_user('Clay')
    mia = make_user('Mia')
    db.create_saved_search(clay['id'], 'Clay only')
    assert db.list_saved_searches(mia['id']) == []


def test_routes_create_list_delete(client, make_user):
    make_user('Clay'); _login(client)
    resp = client.post('/api/saved-searches',
                       json={'name': 'Pinned ideas', 'tags': ['IDEAS'], 'search': 'x'})
    assert resp.status_code == 201
    sid = resp.get_json()['id']
    listed = client.get('/api/saved-searches').get_json()
    assert listed[0]['name'] == 'Pinned ideas' and listed[0]['tags'] == ['IDEAS']
    assert client.delete(f'/api/saved-searches/{sid}').status_code == 200
    assert client.get('/api/saved-searches').get_json() == []


def test_create_requires_name(client, make_user):
    make_user('Clay'); _login(client)
    assert client.post('/api/saved-searches', json={'tags': []}).status_code == 400


def test_cannot_delete_others(client, make_user):
    owner = make_user('Owner')
    other = make_user('Other')
    s = db.create_saved_search(other['id'], 'Theirs')
    _login(client, 'Owner')
    assert client.delete(f"/api/saved-searches/{s['id']}").status_code == 404
    assert db.get_saved_search(s['id']) is not None


# ── Pin to favorite ──────────────────────────────────────────────────────────

def test_pinned_defaults_false_and_sorts_first(make_user):
    user = make_user('Clay')
    db.create_saved_search(user['id'], 'Zeta')
    b = db.create_saved_search(user['id'], 'Alpha')
    assert b['pinned'] is False
    db.set_saved_search_pinned(b['id'], True)   # pin Alpha
    names = [s['name'] for s in db.list_saved_searches(user['id'])]
    assert names == ['Alpha', 'Zeta']           # pinned first, then by name


def test_pin_route_toggles(client, make_user):
    user = make_user('Clay'); _login(client)
    s = db.create_saved_search(user['id'], 'Work')
    resp = client.patch('/api/saved-searches/' + s['id'], json={'pinned': True})
    assert resp.status_code == 200 and resp.get_json()['pinned'] is True
    assert db.get_saved_search(s['id'])['pinned'] is True
    client.patch('/api/saved-searches/' + s['id'], json={'pinned': False})
    assert db.get_saved_search(s['id'])['pinned'] is False


def test_pin_route_404_for_others(client, make_user):
    other = make_user('Other')
    s = db.create_saved_search(other['id'], 'Theirs')
    make_user('Owner'); _login(client, 'Owner')
    assert client.patch('/api/saved-searches/' + s['id'], json={'pinned': True}).status_code == 404
