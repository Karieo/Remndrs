"""Per-todo due dates: persistence through create/replace, note_to_dict,
the PATCH route, MCP complete_todo (preserves due_at), and the .md writer."""

import database as db
import files
import mcp_server


def _login(client, name='Clay'):
    client.post('/api/auth/login', json={'login': name, 'password': 'pw'})


def test_due_at_persists_and_serializes(make_user):
    user = make_user('Clay')
    note = db.create_note(
        user['id'], content='Groceries', note_type='todo',
        todos=[{'text': 'milk', 'checked': False, 'due_at': '2026-07-01'},
               {'text': 'eggs', 'checked': False}])
    todos = db.get_note(note['id'])['todos']
    assert todos[0]['due_at'] == '2026-07-01'
    assert todos[1]['due_at'] is None


def test_patch_route_roundtrips_due(client, make_user):
    user = make_user('Clay'); _login(client)
    note = db.create_note(user['id'], content='List', note_type='todo',
                          todos=[{'text': 'a', 'checked': False}])
    resp = client.patch('/api/notes/' + note['id'], json={'todos': [
        {'text': 'a', 'checked': False, 'due_at': '2026-08-15T09:00'}]})
    assert resp.status_code == 200
    assert resp.get_json()['todos'][0]['due_at'] == '2026-08-15T09:00'


def test_complete_todo_preserves_due(make_user):
    user = make_user('Clay')
    note = db.create_note(user['id'], content='List', note_type='todo',
                          todos=[{'text': 'pay rent', 'checked': False,
                                  'due_at': '2026-07-01'}])
    mcp_server._tool_complete_todo(user, {'note_id': note['id'], 'item': 'rent'})
    todo = db.get_note(note['id'])['todos'][0]
    assert todo['checked'] is True
    assert todo['due_at'] == '2026-07-01'   # not wiped by the toggle


def test_md_body_includes_due_date():
    body = files._note_body({
        'content': 'Groceries',
        'todos': [{'text': 'milk', 'checked': False, 'due_at': '2026-07-01'}],
        'replies': [],
    })
    assert '- [ ] milk 📅 2026-07-01' in body
