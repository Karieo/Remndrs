"""Hidden-contents flag on notes: default, persistence via PATCH, serialization,
.md frontmatter, and migration onto an old notes table."""

import sqlite3
import tempfile

import database as db
import files


def _login(client, name='Clay'):
    client.post('/api/auth/login', json={'login': name, 'password': 'pw'})


def test_hidden_defaults_false_and_serializes(make_user, make_note):
    user = make_user('Clay')
    note = make_note(user, content='secret recipe')
    assert db.get_note(note['id'])['hidden'] is False


def test_patch_toggles_hidden(client, make_user, make_note):
    user = make_user('Clay'); _login(client)
    note = make_note(user, content='private stuff')
    resp = client.patch('/api/notes/' + note['id'], json={'hidden': True})
    assert resp.status_code == 200
    assert resp.get_json()['hidden'] is True
    assert db.get_note(note['id'])['hidden'] is True
    # ...and back off
    client.patch('/api/notes/' + note['id'], json={'hidden': False})
    assert db.get_note(note['id'])['hidden'] is False


def test_hidden_in_frontmatter():
    fm = files._frontmatter({
        'id': 'n1', 'feed': 'private', 'source': 'web', 'pinned': False,
        'archived': False, 'hidden': True, 'tags': [],
        'created_at': '2026-06-15T09:00', 'updated_at': '2026-06-15T09:00',
    }, 'Clay')
    assert 'hidden: true' in fm


def test_migration_adds_hidden_to_old_notes_table():
    path = tempfile.mktemp(suffix='.db')
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE notes (id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
      feed TEXT, type TEXT, content TEXT, source TEXT, pinned INTEGER DEFAULT 0,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, filename TEXT)""")
    conn.execute("INSERT INTO notes (id,user_id,content,created_at,updated_at) "
                 "VALUES ('n','u','old note','t','t')")
    conn.commit(); conn.close()
    orig = db.DB_PATH
    try:
        db.DB_PATH = path
        db.init_db()
        cols = [r[1] for r in sqlite3.connect(path).execute('PRAGMA table_info(notes)')]
        assert 'hidden' in cols
        row = sqlite3.connect(path).execute("SELECT content FROM notes WHERE id='n'").fetchone()
        assert row[0] == 'old note'   # data preserved
    finally:
        db.DB_PATH = orig
