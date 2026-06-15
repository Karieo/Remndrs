"""Per-note custom accent color: PATCH set/clear, serialization, .md
frontmatter, and migration onto an old notes table."""

import sqlite3
import tempfile

import database as db
import files


def _login(client, name='Clay'):
    client.post('/api/auth/login', json={'login': name, 'password': 'pw'})


def test_color_defaults_none(make_user, make_note):
    user = make_user('Clay')
    assert db.get_note(make_note(user, content='x')['id'])['color'] is None


def test_patch_set_and_clear_color(client, make_user, make_note):
    user = make_user('Clay'); _login(client)
    note = make_note(user, content='x')
    resp = client.patch('/api/notes/' + note['id'], json={'color': '#60a5fa'})
    assert resp.status_code == 200 and resp.get_json()['color'] == '#60a5fa'
    assert db.get_note(note['id'])['color'] == '#60a5fa'
    # null clears it
    client.patch('/api/notes/' + note['id'], json={'color': None})
    assert db.get_note(note['id'])['color'] is None


def test_color_in_frontmatter_only_when_set():
    base = {'id': 'n', 'feed': 'private', 'source': 'web', 'pinned': False,
            'archived': False, 'hidden': False, 'tags': [],
            'created_at': 't', 'updated_at': 't'}
    assert 'color:' not in files._frontmatter(base, 'Clay')
    assert 'color: "#f87171"' in files._frontmatter({**base, 'color': '#f87171'}, 'Clay')


def test_migration_adds_color():
    path = tempfile.mktemp(suffix='.db')
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE notes (id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
      feed TEXT, type TEXT, content TEXT, source TEXT, pinned INTEGER DEFAULT 0,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, filename TEXT)""")
    conn.commit(); conn.close()
    orig = db.DB_PATH
    try:
        db.DB_PATH = path
        db.init_db()
        cols = [r[1] for r in sqlite3.connect(path).execute('PRAGMA table_info(notes)')]
        assert 'color' in cols
    finally:
        db.DB_PATH = orig
