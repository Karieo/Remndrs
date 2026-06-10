"""SQLite schema and all query functions for Remndrs."""

import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'remndrs.db')

DEFAULT_PALETTE = [
    '#4ade80',  # green
    '#f87171',  # red
    '#60a5fa',  # blue
    '#fb923c',  # orange
    '#a78bfa',  # purple
    '#facc15',  # yellow
    '#f472b6',  # pink
    '#2dd4bf',  # teal
    '#e5e7eb',  # white
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE,
  phone_number TEXT,
  twilio_number TEXT,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'member',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  feed TEXT NOT NULL DEFAULT 'private',
  type TEXT NOT NULL DEFAULT 'note',
  content TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'web',
  pinned INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  filename TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  color TEXT NOT NULL DEFAULT '#4ade80',
  created_by TEXT
);

CREATE TABLE IF NOT EXISTS note_tags (
  note_id TEXT NOT NULL,
  tag_id INTEGER NOT NULL,
  PRIMARY KEY (note_id, tag_id),
  FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS todo_items (
  id TEXT PRIMARY KEY,
  note_id TEXT NOT NULL,
  text TEXT NOT NULL,
  checked INTEGER NOT NULL DEFAULT 0,
  position INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reminders (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  note_id TEXT,
  message TEXT NOT NULL,
  fire_at TEXT NOT NULL,
  notify_sms INTEGER NOT NULL DEFAULT 1,
  notify_web INTEGER NOT NULL DEFAULT 1,
  fired INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS attachments (
  id TEXT PRIMARY KEY,
  note_id TEXT NOT NULL,
  original_filename TEXT NOT NULL,
  saved_filename TEXT NOT NULL,
  mime_type TEXT,
  size_bytes INTEGER,
  created_at TEXT NOT NULL,
  FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS link_previews (
  url TEXT PRIMARY KEY,
  title TEXT,
  description TEXT,
  image TEXT,
  favicon TEXT,
  site_name TEXT,
  fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_events (
  id TEXT PRIMARY KEY,
  uid TEXT NOT NULL UNIQUE,
  calendar_name TEXT NOT NULL,
  user_id TEXT NOT NULL,
  feed TEXT NOT NULL DEFAULT 'private',
  title TEXT NOT NULL,
  location TEXT,
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  all_day INTEGER NOT NULL DEFAULT 0,
  etag TEXT,
  last_synced_at TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS calendar_notes (
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  filename TEXT,
  FOREIGN KEY (event_id) REFERENCES calendar_events(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS calendar_note_tags (
  calendar_note_id TEXT NOT NULL,
  tag_id INTEGER NOT NULL,
  PRIMARY KEY (calendar_note_id, tag_id),
  FOREIGN KEY (calendar_note_id) REFERENCES calendar_notes(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_calendar_prefs (
  user_id TEXT NOT NULL,
  calendar_name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  feed TEXT NOT NULL DEFAULT 'private',
  PRIMARY KEY (user_id, calendar_name),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS user_caldav_credentials (
  user_id TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  password_encrypted TEXT NOT NULL,
  last_sync_at TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS api_tokens (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  device_name TEXT,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS note_calendar_links (
  note_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (note_id, event_id),
  FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE,
  FOREIGN KEY (event_id) REFERENCES calendar_events(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
  content,
  content='notes',
  content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
  INSERT INTO notes_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
  INSERT INTO notes_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
END;
"""


def now_iso():
    return datetime.now().isoformat(timespec='seconds')


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


def normalize_tag(name):
    return name.strip().lstrip('#').strip().upper()


# ── Users ────────────────────────────────────────────────

def create_user(name, password_hash, email=None, phone_number=None,
                twilio_number=None, role='member'):
    user_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            'INSERT INTO users (id, name, email, phone_number, twilio_number, '
            'password_hash, role, created_at) VALUES (?,?,?,?,?,?,?,?)',
            (user_id, name, email, phone_number, twilio_number,
             password_hash, role, now_iso()))
    return get_user(user_id)


def get_user(user_id):
    with connect() as conn:
        row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_login(login):
    with connect() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE lower(name) = lower(?) OR lower(email) = lower(?)',
            (login, login)).fetchone()
    return dict(row) if row else None


def get_user_by_twilio_number(number):
    with connect() as conn:
        row = conn.execute('SELECT * FROM users WHERE twilio_number = ?', (number,)).fetchone()
    return dict(row) if row else None


def get_user_by_email(email):
    with connect() as conn:
        row = conn.execute('SELECT * FROM users WHERE lower(email) = lower(?)', (email,)).fetchone()
    return dict(row) if row else None


def list_users():
    with connect() as conn:
        rows = conn.execute('SELECT * FROM users').fetchall()
    return [dict(r) for r in rows]


def count_users():
    with connect() as conn:
        return conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]


# ── API tokens ───────────────────────────────────────────

def create_api_token(user_id, token_hash, device_name=None):
    token_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            'INSERT INTO api_tokens (id, user_id, token_hash, device_name, created_at) '
            'VALUES (?,?,?,?,?)',
            (token_id, user_id, token_hash, device_name, now_iso()))
        row = conn.execute('SELECT * FROM api_tokens WHERE id = ?', (token_id,)).fetchone()
    return dict(row)


def get_user_by_token_hash(token_hash):
    with connect() as conn:
        row = conn.execute(
            'SELECT u.* FROM api_tokens t JOIN users u ON u.id = t.user_id '
            'WHERE t.token_hash = ?', (token_hash,)).fetchone()
        if row:
            conn.execute('UPDATE api_tokens SET last_used_at = ? WHERE token_hash = ?',
                         (now_iso(), token_hash))
    return dict(row) if row else None


def list_api_tokens(user_id):
    with connect() as conn:
        rows = conn.execute(
            'SELECT id, device_name, created_at, last_used_at FROM api_tokens '
            'WHERE user_id = ? ORDER BY created_at', (user_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_api_token_by_hash(token_hash):
    with connect() as conn:
        conn.execute('DELETE FROM api_tokens WHERE token_hash = ?', (token_hash,))


# ── Tags ─────────────────────────────────────────────────

def list_tags():
    with connect() as conn:
        rows = conn.execute(
            'SELECT t.id, t.name, t.color, COUNT(nt.note_id) AS count '
            'FROM tags t LEFT JOIN note_tags nt ON nt.tag_id = t.id '
            'GROUP BY t.id ORDER BY count DESC, t.name').fetchall()
    return [dict(r) for r in rows]


def get_tag_by_name(name):
    with connect() as conn:
        row = conn.execute('SELECT * FROM tags WHERE name = ?', (normalize_tag(name),)).fetchone()
    return dict(row) if row else None


def create_tag(name, color=None, created_by=None):
    name = normalize_tag(name)
    if not name:
        return None
    existing = get_tag_by_name(name)
    if existing:
        return existing
    if not color:
        with connect() as conn:
            n = conn.execute('SELECT COUNT(*) FROM tags').fetchone()[0]
        color = DEFAULT_PALETTE[n % len(DEFAULT_PALETTE)]
    with connect() as conn:
        cur = conn.execute('INSERT INTO tags (name, color, created_by) VALUES (?,?,?)',
                           (name, color, created_by))
        tag_id = cur.lastrowid
    return {'id': tag_id, 'name': name, 'color': color}


def update_tag(tag_id, name=None, color=None):
    with connect() as conn:
        if name:
            conn.execute('UPDATE tags SET name = ? WHERE id = ?', (normalize_tag(name), tag_id))
        if color:
            conn.execute('UPDATE tags SET color = ? WHERE id = ?', (color, tag_id))
        row = conn.execute('SELECT * FROM tags WHERE id = ?', (tag_id,)).fetchone()
    return dict(row) if row else None


def delete_tag(tag_id):
    with connect() as conn:
        conn.execute('DELETE FROM tags WHERE id = ?', (tag_id,))


def get_note_tags(note_id):
    with connect() as conn:
        rows = conn.execute(
            'SELECT t.name, t.color FROM note_tags nt '
            'JOIN tags t ON t.id = nt.tag_id WHERE nt.note_id = ? ORDER BY nt.rowid',
            (note_id,)).fetchall()
    return [dict(r) for r in rows]


def set_note_tags(note_id, tag_names, created_by=None):
    with connect() as conn:
        conn.execute('DELETE FROM note_tags WHERE note_id = ?', (note_id,))
    seen = set()
    for raw in tag_names or []:
        name = normalize_tag(raw)
        if not name or name in seen:
            continue
        seen.add(name)
        tag = create_tag(name, created_by=created_by)
        with connect() as conn:
            conn.execute('INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)',
                         (note_id, tag['id']))


# ── Notes ────────────────────────────────────────────────

def note_to_dict(row):
    note = dict(row)
    note['pinned'] = bool(note['pinned'])
    note['tags'] = get_note_tags(note['id'])
    with connect() as conn:
        todos = conn.execute(
            'SELECT id, text, checked, position FROM todo_items '
            'WHERE note_id = ? ORDER BY position', (note['id'],)).fetchall()
        atts = conn.execute(
            'SELECT id, original_filename, saved_filename, mime_type, size_bytes '
            'FROM attachments WHERE note_id = ? ORDER BY created_at', (note['id'],)).fetchall()
    note['todos'] = [{**dict(t), 'checked': bool(t['checked'])} for t in todos]
    note['attachments'] = [dict(a) for a in atts]
    return note


def create_note(user_id, content='', note_type='note', feed='private',
                source='web', pinned=False, filename=None, tags=None, todos=None):
    note_id = str(uuid.uuid4())
    ts = now_iso()
    with connect() as conn:
        conn.execute(
            'INSERT INTO notes (id, user_id, feed, type, content, source, pinned, '
            'created_at, updated_at, filename) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (note_id, user_id, feed, note_type, content, source,
             1 if pinned else 0, ts, ts, filename))
    set_note_tags(note_id, tags, created_by=user_id)
    replace_todos(note_id, todos)
    return get_note(note_id)


def get_note(note_id):
    with connect() as conn:
        row = conn.execute('SELECT * FROM notes WHERE id = ?', (note_id,)).fetchone()
    return note_to_dict(row) if row else None


def update_note(note_id, **fields):
    allowed = {'content', 'feed', 'type', 'pinned', 'filename', 'source'}
    sets, params = [], []
    for key, value in fields.items():
        if key in allowed:
            sets.append(f'{key} = ?')
            params.append(1 if (key == 'pinned' and value) else
                          (0 if key == 'pinned' else value))
    sets.append('updated_at = ?')
    params.append(now_iso())
    params.append(note_id)
    with connect() as conn:
        conn.execute(f'UPDATE notes SET {", ".join(sets)} WHERE id = ?', params)
    if 'tags' in fields:
        set_note_tags(note_id, fields['tags'])
    return get_note(note_id)


def delete_note(note_id):
    with connect() as conn:
        conn.execute('DELETE FROM notes WHERE id = ?', (note_id,))


def replace_todos(note_id, todos):
    if todos is None:
        return
    with connect() as conn:
        conn.execute('DELETE FROM todo_items WHERE note_id = ?', (note_id,))
        for i, todo in enumerate(todos):
            conn.execute(
                'INSERT INTO todo_items (id, note_id, text, checked, position) '
                'VALUES (?,?,?,?,?)',
                (str(uuid.uuid4()), note_id, todo.get('text', ''),
                 1 if todo.get('checked') else 0, i))


def _fts_query(search):
    tokens = re.findall(r'\w+', search)
    return ' '.join(f'"{t}"' for t in tokens) if tokens else None


def list_notes(user_id, tag=None, search=None, source=None, feed=None):
    sql = ('SELECT DISTINCT n.* FROM notes n ')
    where = ["(n.user_id = ? AND n.feed = 'private') OR n.feed = 'shared'"]
    params = [user_id]

    if tag:
        sql += ('JOIN note_tags nt ON nt.note_id = n.id '
                'JOIN tags t ON t.id = nt.tag_id ')
        where.append('t.name = ?')
        params.append(normalize_tag(tag))
    if source:
        where.append('n.source = ?')
        params.append(source)
    if feed in ('private', 'shared'):
        where.append('n.feed = ?')
        params.append(feed)
    if search:
        fts = _fts_query(search)
        if fts:
            sql += 'JOIN notes_fts f ON f.rowid = n.rowid '
            where.append('notes_fts MATCH ?')
            params.append(fts)

    sql += 'WHERE (' + ') AND ('.join(where) + ') '
    sql += 'ORDER BY n.pinned DESC, n.created_at DESC'
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [note_to_dict(r) for r in rows]


def search_user_notes(user_id, search, limit=3):
    fts = _fts_query(search)
    if not fts:
        return []
    with connect() as conn:
        rows = conn.execute(
            'SELECT n.* FROM notes n JOIN notes_fts f ON f.rowid = n.rowid '
            'WHERE n.user_id = ? AND notes_fts MATCH ? '
            'ORDER BY n.created_at DESC LIMIT ?',
            (user_id, fts, limit)).fetchall()
    return [note_to_dict(r) for r in rows]


def notes_by_tag(user_id, tag, limit=3):
    with connect() as conn:
        rows = conn.execute(
            'SELECT n.* FROM notes n '
            'JOIN note_tags nt ON nt.note_id = n.id '
            'JOIN tags t ON t.id = nt.tag_id '
            'WHERE n.user_id = ? AND t.name = ? '
            'ORDER BY n.created_at DESC LIMIT ?',
            (user_id, normalize_tag(tag), limit)).fetchall()
    return [note_to_dict(r) for r in rows]


def recent_notes(user_id, limit=5):
    with connect() as conn:
        rows = conn.execute(
            'SELECT * FROM notes WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
            (user_id, limit)).fetchall()
    return [note_to_dict(r) for r in rows]


# ── Attachments ──────────────────────────────────────────

def add_attachment(note_id, original_filename, saved_filename, mime_type, size_bytes):
    att_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            'INSERT INTO attachments (id, note_id, original_filename, saved_filename, '
            'mime_type, size_bytes, created_at) VALUES (?,?,?,?,?,?,?)',
            (att_id, note_id, original_filename, saved_filename,
             mime_type, size_bytes, now_iso()))
    return att_id


def get_attachment_by_filename(saved_filename):
    with connect() as conn:
        row = conn.execute(
            'SELECT a.*, n.user_id, n.feed FROM attachments a '
            'JOIN notes n ON n.id = a.note_id WHERE a.saved_filename = ?',
            (saved_filename,)).fetchone()
    return dict(row) if row else None


# ── Reminders ────────────────────────────────────────────

def create_reminder(user_id, message, fire_at, notify_sms=True, notify_web=True, note_id=None):
    rem_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            'INSERT INTO reminders (id, user_id, note_id, message, fire_at, '
            'notify_sms, notify_web, fired, created_at) VALUES (?,?,?,?,?,?,?,0,?)',
            (rem_id, user_id, note_id, message, fire_at,
             1 if notify_sms else 0, 1 if notify_web else 0, now_iso()))
    return get_reminder(rem_id)


def get_reminder(rem_id):
    with connect() as conn:
        row = conn.execute('SELECT * FROM reminders WHERE id = ?', (rem_id,)).fetchone()
    return dict(row) if row else None


def list_reminders(user_id):
    with connect() as conn:
        rows = conn.execute(
            'SELECT * FROM reminders WHERE user_id = ? AND fired = 0 ORDER BY fire_at',
            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def pending_reminders(user_id):
    """Reminders fired in the last 24h — SSE fallback for tabs that missed the push."""
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat(timespec='seconds')
    with connect() as conn:
        rows = conn.execute(
            'SELECT * FROM reminders WHERE user_id = ? AND fired = 1 AND fire_at >= ? '
            'ORDER BY fire_at DESC', (user_id, cutoff)).fetchall()
    return [dict(r) for r in rows]


def delete_reminder(rem_id):
    with connect() as conn:
        conn.execute('DELETE FROM reminders WHERE id = ?', (rem_id,))


def get_due_reminders(now):
    with connect() as conn:
        rows = conn.execute(
            'SELECT * FROM reminders WHERE fire_at <= ? AND fired = 0', (now,)).fetchall()
    return [dict(r) for r in rows]


def mark_reminder_fired(rem_id):
    with connect() as conn:
        conn.execute('UPDATE reminders SET fired = 1 WHERE id = ?', (rem_id,))


# ── Link previews ────────────────────────────────────────

def get_link_preview(url):
    with connect() as conn:
        row = conn.execute('SELECT * FROM link_previews WHERE url = ?', (url,)).fetchone()
    return dict(row) if row else None


def save_link_preview(url, title, description, image, favicon, site_name):
    with connect() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO link_previews '
            '(url, title, description, image, favicon, site_name, fetched_at) '
            'VALUES (?,?,?,?,?,?,?)',
            (url, title, description, image, favicon, site_name, now_iso()))


# ── Calendar events ──────────────────────────────────────

def get_calendar_event(event_id):
    with connect() as conn:
        row = conn.execute('SELECT * FROM calendar_events WHERE id = ?', (event_id,)).fetchone()
    return dict(row) if row else None


def get_calendar_event_by_uid(uid):
    with connect() as conn:
        row = conn.execute('SELECT * FROM calendar_events WHERE uid = ?', (uid,)).fetchone()
    return dict(row) if row else None


def insert_calendar_event(uid, calendar_name, user_id, feed, title, location,
                          start_at, end_at, all_day, etag):
    event_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            'INSERT INTO calendar_events (id, uid, calendar_name, user_id, feed, title, '
            'location, start_at, end_at, all_day, etag, last_synced_at, deleted) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)',
            (event_id, uid, calendar_name, user_id, feed, title, location,
             start_at, end_at, 1 if all_day else 0, etag, now_iso()))
    return get_calendar_event(event_id)


def update_calendar_event(event_id, title, location, start_at, end_at, all_day, etag):
    with connect() as conn:
        conn.execute(
            'UPDATE calendar_events SET title=?, location=?, start_at=?, end_at=?, '
            'all_day=?, etag=?, last_synced_at=? WHERE id=?',
            (title, location, start_at, end_at, 1 if all_day else 0,
             etag, now_iso(), event_id))
    return get_calendar_event(event_id)


def mark_event_deleted(event_id):
    with connect() as conn:
        conn.execute('UPDATE calendar_events SET deleted = 1, last_synced_at = ? WHERE id = ?',
                     (now_iso(), event_id))


def list_calendar_events(user_id, start, end):
    """Events visible to a user: own private + anyone's shared, in [start, end)."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM calendar_events WHERE "
            "((user_id = ? AND feed = 'private') OR feed = 'shared') "
            "AND start_at < ? AND end_at >= ? ORDER BY start_at",
            (user_id, end, start)).fetchall()
    return [dict(r) for r in rows]


def event_uids_in_window(user_id, calendar_name, start, end):
    with connect() as conn:
        rows = conn.execute(
            'SELECT uid, id FROM calendar_events WHERE user_id = ? AND calendar_name = ? '
            'AND deleted = 0 AND start_at < ? AND end_at >= ?',
            (user_id, calendar_name, end, start)).fetchall()
    return {r['uid']: r['id'] for r in rows}


# ── Calendar notes ───────────────────────────────────────

def get_calendar_note(cal_note_id):
    with connect() as conn:
        row = conn.execute('SELECT * FROM calendar_notes WHERE id = ?', (cal_note_id,)).fetchone()
    if not row:
        return None
    note = dict(row)
    note['tags'] = get_calendar_note_tags(cal_note_id)
    return note


def get_calendar_note_tags(cal_note_id):
    with connect() as conn:
        rows = conn.execute(
            'SELECT t.name, t.color FROM calendar_note_tags cnt '
            'JOIN tags t ON t.id = cnt.tag_id WHERE cnt.calendar_note_id = ? '
            'ORDER BY cnt.rowid', (cal_note_id,)).fetchall()
    return [dict(r) for r in rows]


def set_calendar_note_tags(cal_note_id, tag_names, created_by=None):
    with connect() as conn:
        conn.execute('DELETE FROM calendar_note_tags WHERE calendar_note_id = ?', (cal_note_id,))
    for raw in tag_names or []:
        tag = create_tag(raw, created_by=created_by)
        if tag:
            with connect() as conn:
                conn.execute(
                    'INSERT OR IGNORE INTO calendar_note_tags (calendar_note_id, tag_id) '
                    'VALUES (?,?)', (cal_note_id, tag['id']))


def create_calendar_note(event_id, user_id, content, tags=None, filename=None):
    note_id = str(uuid.uuid4())
    ts = now_iso()
    with connect() as conn:
        conn.execute(
            'INSERT INTO calendar_notes (id, event_id, user_id, content, created_at, '
            'updated_at, filename) VALUES (?,?,?,?,?,?,?)',
            (note_id, event_id, user_id, content, ts, ts, filename))
    set_calendar_note_tags(note_id, tags, created_by=user_id)
    return get_calendar_note(note_id)


def update_calendar_note(cal_note_id, content=None, tags=None, filename=None):
    with connect() as conn:
        if content is not None:
            conn.execute('UPDATE calendar_notes SET content = ?, updated_at = ? WHERE id = ?',
                         (content, now_iso(), cal_note_id))
        if filename is not None:
            conn.execute('UPDATE calendar_notes SET filename = ? WHERE id = ?',
                         (filename, cal_note_id))
    if tags is not None:
        set_calendar_note_tags(cal_note_id, tags)
    return get_calendar_note(cal_note_id)


def delete_calendar_note(cal_note_id):
    with connect() as conn:
        conn.execute('DELETE FROM calendar_notes WHERE id = ?', (cal_note_id,))


def list_calendar_notes(event_id):
    with connect() as conn:
        rows = conn.execute(
            'SELECT * FROM calendar_notes WHERE event_id = ? ORDER BY created_at',
            (event_id,)).fetchall()
    notes = []
    for r in rows:
        note = dict(r)
        note['tags'] = get_calendar_note_tags(note['id'])
        notes.append(note)
    return notes


def tag_calendar_notes_orphaned(event_id):
    tag = create_tag('ORPHANED', color='#f97316')
    with connect() as conn:
        rows = conn.execute('SELECT id FROM calendar_notes WHERE event_id = ?',
                            (event_id,)).fetchall()
        for r in rows:
            conn.execute(
                'INSERT OR IGNORE INTO calendar_note_tags (calendar_note_id, tag_id) '
                'VALUES (?,?)', (r['id'], tag['id']))


# ── Calendar prefs / credentials ─────────────────────────

def get_calendar_prefs(user_id):
    with connect() as conn:
        rows = conn.execute(
            'SELECT calendar_name, enabled, feed FROM user_calendar_prefs WHERE user_id = ? '
            'ORDER BY calendar_name', (user_id,)).fetchall()
    return [{**dict(r), 'enabled': bool(r['enabled'])} for r in rows]


def upsert_calendar_pref(user_id, calendar_name, enabled=None, feed=None):
    with connect() as conn:
        existing = conn.execute(
            'SELECT * FROM user_calendar_prefs WHERE user_id = ? AND calendar_name = ?',
            (user_id, calendar_name)).fetchone()
        if existing is None:
            conn.execute(
                'INSERT INTO user_calendar_prefs (user_id, calendar_name, enabled, feed) '
                'VALUES (?,?,?,?)',
                (user_id, calendar_name,
                 1 if enabled else 0 if enabled is not None else 0,
                 feed or 'private'))
        else:
            if enabled is not None:
                conn.execute(
                    'UPDATE user_calendar_prefs SET enabled = ? WHERE user_id = ? '
                    'AND calendar_name = ?',
                    (1 if enabled else 0, user_id, calendar_name))
            if feed is not None:
                conn.execute(
                    'UPDATE user_calendar_prefs SET feed = ? WHERE user_id = ? '
                    'AND calendar_name = ?', (feed, user_id, calendar_name))


def enabled_calendars(user_id):
    with connect() as conn:
        rows = conn.execute(
            'SELECT calendar_name, feed FROM user_calendar_prefs '
            'WHERE user_id = ? AND enabled = 1', (user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_caldav_credentials(user_id):
    with connect() as conn:
        row = conn.execute('SELECT * FROM user_caldav_credentials WHERE user_id = ?',
                           (user_id,)).fetchone()
    return dict(row) if row else None


def set_caldav_credentials(user_id, username, password_encrypted):
    with connect() as conn:
        conn.execute(
            'INSERT INTO user_caldav_credentials (user_id, username, password_encrypted) '
            'VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET '
            'username = excluded.username, password_encrypted = excluded.password_encrypted',
            (user_id, username, password_encrypted))


def set_caldav_last_sync(user_id):
    with connect() as conn:
        conn.execute('UPDATE user_caldav_credentials SET last_sync_at = ? WHERE user_id = ?',
                     (now_iso(), user_id))


def users_with_caldav():
    with connect() as conn:
        rows = conn.execute('SELECT user_id FROM user_caldav_credentials').fetchall()
    return [r['user_id'] for r in rows]


# ── Note ↔ calendar links ───────────────────────────────

def link_note_to_event(note_id, event_id):
    with connect() as conn:
        conn.execute(
            'INSERT OR IGNORE INTO note_calendar_links (note_id, event_id, created_at) '
            'VALUES (?,?,?)', (note_id, event_id, now_iso()))


def note_event_links(note_id):
    with connect() as conn:
        rows = conn.execute('SELECT event_id FROM note_calendar_links WHERE note_id = ?',
                            (note_id,)).fetchall()
    return [r['event_id'] for r in rows]
