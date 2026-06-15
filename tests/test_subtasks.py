"""Sub-task nesting: the per-todo `indent` level persists through create/replace,
note_to_dict, the PATCH route, MCP complete_todo, the .md writer, and migration."""

import sqlite3
import tempfile

import database as db
import files
import mcp_server


def _login(client, name='Clay'):
    client.post('/api/auth/login', json={'login': name, 'password': 'pw'})


def test_indent_persists_and_serializes(make_user):
    user = make_user('Clay')
    note = db.create_note(user['id'], content='Plan', note_type='todo', todos=[
        {'text': 'parent', 'checked': False, 'indent': 0},
        {'text': 'child', 'checked': False, 'indent': 1},
        {'text': 'flat'},  # missing indent -> 0
    ])
    todos = db.get_note(note['id'])['todos']
    assert [t['indent'] for t in todos] == [0, 1, 0]


def test_indent_clamped_0_to_4(make_user):
    user = make_user('Clay')
    note = db.create_note(user['id'], content='x', note_type='todo',
                          todos=[{'text': 'deep', 'indent': 99},
                                 {'text': 'neg', 'indent': -3}])
    assert [t['indent'] for t in db.get_note(note['id'])['todos']] == [4, 0]


def test_patch_route_roundtrips_indent(client, make_user):
    user = make_user('Clay'); _login(client)
    note = db.create_note(user['id'], content='L', note_type='todo',
                          todos=[{'text': 'a'}])
    resp = client.patch('/api/notes/' + note['id'], json={'todos': [
        {'text': 'a', 'checked': False, 'indent': 2}]})
    assert resp.get_json()['todos'][0]['indent'] == 2


def test_complete_todo_preserves_indent(make_user):
    user = make_user('Clay')
    note = db.create_note(user['id'], content='L', note_type='todo',
                          todos=[{'text': 'sub', 'checked': False, 'indent': 1}])
    mcp_server._tool_complete_todo(user, {'note_id': note['id'], 'item': 'sub'})
    t = db.get_note(note['id'])['todos'][0]
    assert t['checked'] is True and t['indent'] == 1


def test_md_body_indents_subtasks():
    body = files._note_body({
        'content': 'Plan',
        'todos': [{'text': 'parent', 'checked': False, 'indent': 0},
                  {'text': 'child', 'checked': True, 'indent': 1}],
        'replies': [],
    })
    assert '- [ ] parent' in body
    assert '  - [x] child' in body   # two-space indent for one nesting level


def test_migration_adds_indent():
    path = tempfile.mktemp(suffix='.db')
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE todo_items (id TEXT PRIMARY KEY, note_id TEXT NOT NULL,
      text TEXT NOT NULL, checked INTEGER DEFAULT 0, position INTEGER DEFAULT 0)""")
    conn.commit(); conn.close()
    orig = db.DB_PATH
    try:
        db.DB_PATH = path
        db.init_db()
        cols = [r[1] for r in sqlite3.connect(path).execute('PRAGMA table_info(todo_items)')]
        assert 'indent' in cols
    finally:
        db.DB_PATH = orig
