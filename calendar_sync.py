"""CalDAV connection, discovery, two-way iCloud Calendar sync.

iCloud → Remndrs: events appear as cards; updates reflect within 10 minutes.
Remndrs → iCloud: notes can be pushed as new calendar events.
Attached notes and tags never modify the CalDAV event.
"""

import logging
import os
import re
import uuid
from datetime import date, datetime, timedelta

import database as db
import files
import sse

log = logging.getLogger(__name__)

CALDAV_URL = os.getenv('CALDAV_URL', 'https://caldav.icloud.com')

SYNC_PAST_DAYS = 7
SYNC_FUTURE_DAYS = 30


# ── Credential encryption ────────────────────────────────

def get_fernet():
    from cryptography.fernet import Fernet
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        raise ValueError('ENCRYPTION_KEY not set in .env')
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return get_fernet().decrypt(ciphertext.encode()).decode()


def caldav_configured():
    return bool(os.getenv('CALDAV_USERNAME') and os.getenv('CALDAV_PASSWORD'))


def _credentials_for_user(user_id):
    """Per-user stored credentials, falling back to .env for the owner."""
    creds = db.get_caldav_credentials(user_id)
    if creds:
        try:
            return creds['username'], decrypt(creds['password_encrypted'])
        except Exception:
            log.warning('Could not decrypt CalDAV credentials for user %s', user_id)
            return None, None
    user = db.get_user(user_id)
    if user and user.get('role') == 'owner' and caldav_configured():
        return os.getenv('CALDAV_USERNAME'), os.getenv('CALDAV_PASSWORD')
    return None, None


def get_client(username: str, password: str):
    """Return authenticated CalDAV client or None if credentials missing."""
    if not username or not password:
        return None
    import caldav
    return caldav.DAVClient(url=CALDAV_URL, username=username, password=password)


def _principal_calendars(user_id):
    username, password = _credentials_for_user(user_id)
    client = get_client(username, password)
    if not client:
        return None
    return client.principal().calendars()


# ── Discovery ────────────────────────────────────────────

def discover_calendars(user_id):
    """Return all available iCloud calendars for a user.

    Upserts into user_calendar_prefs with enabled=0 if not already present.
    """
    try:
        calendars = _principal_calendars(user_id)
    except Exception:
        log.exception('CalDAV discovery failed for user %s', user_id)
        return []
    if calendars is None:
        return []
    results = []
    for cal in calendars:
        name = str(cal.name or '').strip()
        if not name:
            continue
        results.append({'name': name, 'url': str(cal.url)})
        db.upsert_calendar_pref(user_id, name, enabled=None)
    return results


# ── Sync ─────────────────────────────────────────────────

def sync_all_users():
    """APScheduler entry point — runs every 10 minutes."""
    user_ids = set(db.users_with_caldav())
    if caldav_configured():
        for user in db.list_users():
            if user['role'] == 'owner':
                user_ids.add(user['id'])
    for user_id in user_ids:
        try:
            sync_user_calendars(user_id)
        except Exception:
            log.exception('Calendar sync failed for user %s', user_id)


def sync_user_calendars(user_id):
    """Sync all enabled calendars for a user. Window: today-7d to today+30d."""
    enabled = db.enabled_calendars(user_id)
    if not enabled:
        return
    try:
        calendars = _principal_calendars(user_id)
    except Exception:
        log.exception('CalDAV connection failed for user %s', user_id)
        return
    if calendars is None:
        return

    user = db.get_user(user_id)
    by_name = {str(c.name or '').strip(): c for c in calendars}
    start = datetime.now() - timedelta(days=SYNC_PAST_DAYS)
    end = datetime.now() + timedelta(days=SYNC_FUTURE_DAYS)

    for pref in enabled:
        cal_name, feed = pref['calendar_name'], pref['feed']
        cal_obj = by_name.get(cal_name)
        if cal_obj is None:
            log.warning('Enabled calendar %r not found on server for user %s',
                        cal_name, user_id)
            continue
        try:
            fetched = fetch_events_in_range(cal_obj, start, end)
        except Exception:
            log.exception('Fetch failed for calendar %r', cal_name)
            continue

        seen_uids = set()
        for ev in fetched:
            seen_uids.add(ev['uid'])
            existing = db.get_calendar_event_by_uid(ev['uid'])
            if existing is None:
                created = db.insert_calendar_event(
                    ev['uid'], cal_name, user_id, feed, ev['title'], ev['location'],
                    ev['start_at'], ev['end_at'], ev['all_day'], ev['etag'])
                filename = files.write_event_stub(created, user['name'])
                sse.push_event(user_id, 'calendar_event_created', created)
                _ = filename
            elif existing['etag'] != ev['etag']:
                updated = db.update_calendar_event(
                    existing['id'], ev['title'], ev['location'],
                    ev['start_at'], ev['end_at'], ev['all_day'], ev['etag'])
                files.write_event_stub(updated, user['name'],
                                       existing_filename=_stub_filename(updated, user))
                sse.push_event(user_id, 'calendar_event_updated', updated)

        # Orphan check: events in DB window no longer on the server
        start_iso = start.isoformat(timespec='seconds')
        end_iso = end.isoformat(timespec='seconds')
        db_uids = db.event_uids_in_window(user_id, cal_name, start_iso, end_iso)
        for uid, event_id in db_uids.items():
            if uid not in seen_uids:
                orphan_event(event_id, user_id)

    db.set_caldav_last_sync(user_id)


def _stub_filename(event, user):
    """Find the existing stub file for an event by its UID, if any."""
    folder = files.calendar_folder(user['name'])
    try:
        for fn in os.listdir(folder):
            if not fn.endswith('.md'):
                continue
            with open(os.path.join(folder, fn), encoding='utf-8') as f:
                head = f.read(1024)
            if f'event_uid: {event["uid"]}' in head:
                return fn
    except OSError:
        pass
    return None


def fetch_events_in_range(calendar_obj, start, end):
    """Fetch and parse events, expanding recurrences."""
    results = calendar_obj.date_search(start=start, end=end, expand=True)
    events = []
    from icalendar import Calendar as iCal
    for item in results:
        try:
            etag = getattr(item, 'etag', None) or ''
            cal = iCal.from_ical(item.data)
            for component in cal.walk('VEVENT'):
                parsed = parse_vevent(component)
                if parsed:
                    parsed['etag'] = etag
                    events.append(parsed)
        except Exception:
            log.exception('Could not parse a calendar item')
    return events


def parse_vevent(vevent):
    """Parse a VEVENT. Handles datetime (timed) and date (all-day) DTSTART."""
    uid = str(vevent.get('UID', '')).strip()
    if not uid:
        return None
    title = str(vevent.get('SUMMARY', '')).strip() or '(untitled)'
    location = str(vevent.get('LOCATION', '')).strip() or None

    dtstart = vevent.get('DTSTART')
    dtend = vevent.get('DTEND')
    if dtstart is None:
        return None
    start_val = dtstart.dt
    all_day = isinstance(start_val, date) and not isinstance(start_val, datetime)

    if dtend is not None:
        end_val = dtend.dt
    elif all_day:
        end_val = start_val + timedelta(days=1)
    else:
        end_val = start_val + timedelta(hours=1)

    def to_iso(v):
        if isinstance(v, datetime):
            if v.tzinfo is not None:
                v = v.astimezone().replace(tzinfo=None)
            return v.isoformat(timespec='seconds')
        return datetime(v.year, v.month, v.day).isoformat(timespec='seconds')

    # Recurring instances share a UID — disambiguate with RECURRENCE-ID/start
    recurrence_id = vevent.get('RECURRENCE-ID')
    if recurrence_id is not None:
        uid = f'{uid}::{to_iso(recurrence_id.dt)}'

    return {
        'uid': uid,
        'title': title,
        'location': location,
        'start_at': to_iso(start_val),
        'end_at': to_iso(end_val),
        'all_day': all_day,
    }


# ── Remndrs → iCloud ─────────────────────────────────────

def create_event_from_note(note, user_id, calendar_name, start_at, end_at, all_day):
    """Create a new VEVENT in iCloud from a Remndrs note. Returns the new UID."""
    from icalendar import Calendar as iCal, Event as iCalEvent

    calendars = _principal_calendars(user_id)
    if calendars is None:
        raise ValueError('CalDAV is not configured')
    target = next((c for c in calendars
                   if str(c.name or '').strip() == calendar_name), None)
    if target is None:
        raise ValueError(f'Calendar "{calendar_name}" not found')

    first_line = (note['content'] or '').strip().split('\n')[0]
    summary = re.sub(r'[#*`>\[\]!_~]', '', first_line).strip()[:80] or 'Note'
    uid = f'{uuid.uuid4()}@remndrs'

    cal = iCal()
    cal.add('prodid', '-//Remndrs//EN')
    cal.add('version', '2.0')
    event = iCalEvent()
    event.add('uid', uid)
    event.add('summary', summary)
    event.add('description', note['content'])
    start_dt = datetime.fromisoformat(start_at)
    end_dt = datetime.fromisoformat(end_at)
    if all_day:
        event.add('dtstart', start_dt.date())
        event.add('dtend', end_dt.date() + timedelta(days=1)
                  if end_dt.date() == start_dt.date() else end_dt.date())
    else:
        event.add('dtstart', start_dt)
        event.add('dtend', end_dt)
    event.add('dtstamp', datetime.now())
    cal.add_component(event)

    target.save_event(cal.to_ical().decode())

    user = db.get_user(user_id)
    pref_feed = next((p['feed'] for p in db.enabled_calendars(user_id)
                      if p['calendar_name'] == calendar_name), 'private')
    created = db.insert_calendar_event(
        uid, calendar_name, user_id, pref_feed, summary, None,
        start_dt.isoformat(timespec='seconds'), end_dt.isoformat(timespec='seconds'),
        all_day, None)
    files.write_event_stub(created, user['name'])
    db.link_note_to_event(note['id'], created['id'])
    sse.push_event(user_id, 'calendar_event_created', created)
    return uid


def orphan_event(event_id, user_id):
    """Mark deleted, tag notes #ORPHANED, update stub, push SSE."""
    db.mark_event_deleted(event_id)
    db.tag_calendar_notes_orphaned(event_id)
    event = db.get_calendar_event(event_id)
    user = db.get_user(user_id)
    if event and user:
        notice = (f'> ⚠️ This event was deleted from Apple Calendar '
                  f'on {date.today().isoformat()}.')
        files.write_event_stub(event, user['name'],
                               existing_filename=_stub_filename(event, user),
                               extra_content=notice)
    sse.push_event(user_id, 'calendar_event_orphaned', event or {'id': event_id})
