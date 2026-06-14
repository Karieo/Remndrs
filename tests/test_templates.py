"""Note templates: db CRUD + the /api/templates routes (create/list/delete,
per-user scoping and ownership)."""

import database as db


def _login(client, name='Clay'):
    client.post('/api/auth/login', json={'login': name, 'password': 'pw'})


# ── db ───────────────────────────────────────────────────────────────────────

def test_template_crud(make_user):
    user = make_user('Clay')
    t = db.create_template(user['id'], 'Standup', '## Standup\n- yesterday\n- today')
    assert t['title'] == 'Standup'
    assert [x['id'] for x in db.list_templates(user['id'])] == [t['id']]
    db.delete_template(t['id'])
    assert db.list_templates(user['id']) == []


def test_templates_are_per_user(make_user):
    clay = make_user('Clay')
    mia = make_user('Mia')
    db.create_template(clay['id'], 'Clay tpl', 'x')
    assert db.list_templates(mia['id']) == []


# ── routes ─────────────────────────────────────────────────────────────────

def test_create_list_delete_routes(client, make_user):
    user = make_user('Clay'); _login(client)
    resp = client.post('/api/templates', json={'title': 'Journal', 'body': '# {date}'})
    assert resp.status_code == 201
    tid = resp.get_json()['id']
    assert [t['title'] for t in client.get('/api/templates').get_json()] == ['Journal']
    assert client.delete(f'/api/templates/{tid}').status_code == 200
    assert client.get('/api/templates').get_json() == []


def test_create_requires_title_and_body(client, make_user):
    make_user('Clay'); _login(client)
    assert client.post('/api/templates', json={'title': 'x'}).status_code == 400
    assert client.post('/api/templates', json={'body': 'x'}).status_code == 400


def test_cannot_delete_others_template(client, make_user):
    owner = make_user('Owner')
    other = make_user('Other')
    t = db.create_template(other['id'], 'Theirs', 'body')
    _login(client, 'Owner')
    assert client.delete(f"/api/templates/{t['id']}").status_code == 404
    assert db.get_template(t['id']) is not None   # untouched
