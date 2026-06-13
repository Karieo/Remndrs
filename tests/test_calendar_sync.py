"""Tier 3 — CalDAV calendar sync (calendar_sync.py).

Covers the pure VEVENT parser, credential encryption round-trip + the
decrypt-failure fallback, and the orphan-event path (mark deleted, tag notes
#ORPHANED, regenerate stub with a deletion notice) — all without a live
CalDAV server.
"""

from datetime import date, datetime

import pytest
from cryptography.fernet import Fernet
from icalendar import Event

import calendar_sync as cs
import database as db


# ── parse_vevent ───────────────────────────────────────────────────────────

def _vevent(**adds):
    ev = Event()
    for key, val in adds.items():
        ev.add(key, val)
    return ev


def test_parse_vevent_timed_event():
    ev = _vevent(uid='abc', summary='Standup',
                 dtstart=datetime(2026, 6, 20, 10, 0, 0),
                 dtend=datetime(2026, 6, 20, 10, 30, 0))
    out = cs.parse_vevent(ev)
    assert out['uid'] == 'abc'
    assert out['title'] == 'Standup'
    assert out['all_day'] is False
    assert out['start_at'] == '2026-06-20T10:00:00'
    assert out['end_at'] == '2026-06-20T10:30:00'


def test_parse_vevent_all_day_defaults_end_to_next_day():
    ev = _vevent(uid='d1', summary='Holiday', dtstart=date(2026, 7, 4))
    out = cs.parse_vevent(ev)
    assert out['all_day'] is True
    assert out['start_at'].startswith('2026-07-04')
    assert out['end_at'].startswith('2026-07-05')


def test_parse_vevent_timed_without_dtend_adds_one_hour():
    ev = _vevent(uid='t1', summary='Call', dtstart=datetime(2026, 6, 20, 9, 0, 0))
    out = cs.parse_vevent(ev)
    assert out['end_at'] == '2026-06-20T10:00:00'


def test_parse_vevent_missing_uid_returns_none():
    ev = _vevent(summary='No id', dtstart=datetime(2026, 6, 20, 9, 0, 0))
    assert cs.parse_vevent(ev) is None


def test_parse_vevent_missing_dtstart_returns_none():
    ev = _vevent(uid='x', summary='No start')
    assert cs.parse_vevent(ev) is None


def test_parse_vevent_untitled_default():
    ev = _vevent(uid='u', dtstart=datetime(2026, 6, 20, 9, 0, 0))
    assert cs.parse_vevent(ev)['title'] == '(untitled)'


def test_parse_vevent_recurrence_id_disambiguates_uid():
    ev = _vevent(uid='series', summary='Weekly',
                 dtstart=datetime(2026, 6, 20, 9, 0, 0),
                 dtend=datetime(2026, 6, 20, 9, 30, 0))
    ev.add('recurrence-id', datetime(2026, 6, 20, 9, 0, 0))
    out = cs.parse_vevent(ev)
    assert out['uid'].startswith('series::')


# ── Credential encryption ──────────────────────────────────────────────────

def test_encrypt_decrypt_round_trip(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
    token = cs.encrypt('hunter2')
    assert token != 'hunter2'
    assert cs.decrypt(token) == 'hunter2'


def test_get_fernet_requires_key(monkeypatch):
    monkeypatch.delenv('ENCRYPTION_KEY', raising=False)
    with pytest.raises(ValueError):
        cs.get_fernet()


def test_credentials_for_user_handles_bad_ciphertext(make_user, monkeypatch):
    monkeypatch.setenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
    user = make_user('Clay')
    # Store something that won't decrypt with the current key.
    db.set_caldav_credentials(user['id'], 'clay@icloud.com', 'not-a-valid-token')
    assert cs._credentials_for_user(user['id']) == (None, None)


def test_credentials_for_user_round_trips_stored_creds(make_user, monkeypatch):
    monkeypatch.setenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
    user = make_user('Clay')
    db.set_caldav_credentials(user['id'], 'clay@icloud.com', cs.encrypt('app-pw'))
    assert cs._credentials_for_user(user['id']) == ('clay@icloud.com', 'app-pw')


# ── orphan_event ───────────────────────────────────────────────────────────

def test_orphan_event_marks_deleted_tags_and_writes_notice(make_user, monkeypatch, tmp_path):
    monkeypatch.setenv('NOTES_FOLDER', str(tmp_path / 'notes'))
    import files

    user = make_user('Clay')
    event = db.insert_calendar_event(
        'evt-9', 'Home', user['id'], 'private', 'Dentist', None,
        '2026-06-20T10:00:00', '2026-06-20T11:00:00', False, 'etag1')
    db.create_calendar_note(event['id'], user['id'], 'remember to floss')

    # Pre-create the stub so orphan_event finds and appends to it.
    files.write_event_stub(event, user['name'])

    cs.orphan_event(event['id'], user['id'])

    # 1) event row flagged deleted
    assert db.get_calendar_event(event['id'])['deleted'] == 1
    # 2) attached calendar note tagged #ORPHANED
    cal_note = db.list_calendar_notes(event['id'])[0]
    assert 'ORPHANED' in [t['name'] for t in db.get_calendar_note_tags(cal_note['id'])]
    # 3) stub regenerated with the deletion notice
    fname = cs._stub_filename(event, user)
    assert fname is not None
    text = (tmp_path / 'notes' / 'Clay' / 'Calendar' / fname).read_text()
    assert 'deleted from Apple Calendar' in text
    assert 'remember to floss' not in text  # notice goes below marker, not note body
