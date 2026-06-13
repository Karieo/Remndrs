"""Shared pytest fixtures for the Remndrs test suite.

Isolation strategy
------------------
The app keeps its SQLite path in ``database.DB_PATH`` and reads it lazily in
``connect()``, and every integration reads its credentials with ``os.getenv``
at call time. So before importing the app we:

  * point ``NOTES_FOLDER`` and ``database.DB_PATH`` at a throwaway temp dir, and
  * strip any integration secrets that might have leaked in from a real .env,

then create the schema. ``app`` is imported lazily by the ``client`` fixture so
that pure-logic tests don't pay for (or depend on) the Flask app.

Every test starts with empty tables via the autouse ``reset_db`` fixture, so
tests never see each other's rows.
"""

import os
import sqlite3
import tempfile

import bcrypt
import pytest

# ── One-time environment setup, before any app module is imported ──────────
_TMPDIR = tempfile.mkdtemp(prefix='remndrs-test-')
os.environ['NOTES_FOLDER'] = os.path.join(_TMPDIR, 'notes')
os.environ['SESSION_SECRET'] = 'test-session-secret'
os.environ.setdefault('OWNER_NAME', 'Owner')
os.environ.setdefault('OWNER_PASSWORD', 'ownerpw')
# Make sure no real integration creds bleed in from a developer's shell/.env;
# individual tests opt in explicitly via monkeypatch.setenv.
for _k in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_FROM_NUMBER',
           'MAILGUN_SIGNING_KEY', 'MAILGUN_API_KEY', 'MAILGUN_INBOUND_ADDRESS',
           'TELEGRAM_BOT_TOKEN', 'TELEGRAM_WEBHOOK_SECRET', 'OPENAI_API_KEY'):
    os.environ.pop(_k, None)

import database as db  # noqa: E402  (must follow the env setup above)

db.DB_PATH = os.path.join(_TMPDIR, 'test.db')
db.init_db()


def _all_tables():
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    # Skip sqlite internals and the FTS5 shadow tables (those are maintained by
    # triggers when we clear the base `notes` table).
    return [r['name'] for r in rows
            if not r['name'].startswith('sqlite_') and 'fts' not in r['name']]


@pytest.fixture(autouse=True)
def reset_db():
    """Empty every base table before each test for full isolation."""
    with db.connect() as conn:
        conn.execute('PRAGMA foreign_keys = OFF')
        for table in _all_tables():
            try:
                conn.execute(f'DELETE FROM {table}')
            except sqlite3.OperationalError:
                pass
        conn.execute('PRAGMA foreign_keys = ON')
    yield


@pytest.fixture
def make_user():
    """Factory: create a user row and return its dict."""
    def _make(name, password='pw', role='member', email=None,
              phone_number=None, twilio_number=None):
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        return db.create_user(name, pw_hash, email=email,
                              phone_number=phone_number,
                              twilio_number=twilio_number, role=role)
    return _make


@pytest.fixture
def make_note():
    """Factory: create a note for a user dict."""
    def _make(user, content='hello', feed='private', source='web',
              tags=None, note_type='note', todos=None):
        return db.create_note(user['id'], content=content, feed=feed,
                             source=source, tags=tags, note_type=note_type,
                             todos=todos)
    return _make


@pytest.fixture
def client():
    """Flask test client. Imported lazily so pure-logic tests stay light."""
    import app as appmod
    appmod.app.config['TESTING'] = True
    appmod._AUTH_FAILURES.clear()
    return appmod.app.test_client()
