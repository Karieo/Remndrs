"""APScheduler background jobs: reminder dispatch + calendar sync.
Also the shared natural-language reminder parser used by SMS and email."""

import atexit
import logging
import re
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

import database as db
import sse
import webpush

log = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def parse_remind_text(text):
    """Parse a natural-language reminder like 'remind me Friday 3pm to call'.

    Returns (fire_at_iso, message) or None when no future time is found.
    """
    try:
        from dateparser.search import search_dates
    except ImportError:
        return None
    # Drop the remind phrase first — it throws dateparser off.
    text = re.sub(r'\bremind(er)?( me)?\b\s*:?', '', text, flags=re.IGNORECASE)
    settings = {'PREFER_DATES_FROM': 'future'}
    results = search_dates(text, settings=settings)
    if not results:
        return None
    matched_text, fire_at = results[0]
    # search_dates can mis-parse compound spans ("tomorrow at 9am" → now+1d);
    # re-parsing just the matched span gets the time right.
    import dateparser
    better = dateparser.parse(matched_text, settings=settings)
    if better:
        fire_at = better
    if fire_at <= datetime.now():
        # dateparser matched a stray word as a past time — not a reminder.
        return None
    message = text.replace(matched_text, '', 1)
    message = re.sub(r'^(on|at|to|that)\s+', '',
                     message.strip(' \t-—–:,.'), flags=re.IGNORECASE)
    message = re.sub(r'\s+(next|on|at|this)$', '', message.rstrip(), flags=re.IGNORECASE)
    message = re.sub(r'\s+', ' ', message).strip(' \t-—–:,.')
    return fire_at.isoformat(timespec='seconds'), message


_WEEKDAYS = {'monday': 'MO', 'tuesday': 'TU', 'wednesday': 'WE', 'thursday': 'TH',
             'friday': 'FR', 'saturday': 'SA', 'sunday': 'SU'}


def parse_recurrence(text):
    """Map a natural-language repeat phrase to a stored RRULE, or None.

    Handles 'daily', 'weekly', 'monthly', 'yearly', 'weekdays', and
    'every <weekday>'. Anything else (including a one-off time) returns None."""
    if not text:
        return None
    t = text.lower()
    if re.search(r'\b(weekdays?|every weekday)\b', t):
        return 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR'
    for name, code in _WEEKDAYS.items():
        if re.search(r'\bevery\s+' + name + r's?\b', t):
            return f'FREQ=WEEKLY;BYDAY={code}'
    if re.search(r'\b(daily|every day)\b', t):
        return 'FREQ=DAILY'
    if re.search(r'\b(weekly|every week)\b', t):
        return 'FREQ=WEEKLY'
    if re.search(r'\b(monthly|every month)\b', t):
        return 'FREQ=MONTHLY'
    if re.search(r'\b(yearly|annually|every year)\b', t):
        return 'FREQ=YEARLY'
    return None


def normalize_recurrence(value):
    """Accept either a repeat keyword ('daily', 'every monday', 'weekdays') or a
    raw RRULE string and return a stored RRULE, or None if empty/unrecognised."""
    value = (value or '').strip()
    if not value:
        return None
    # A raw RRULE (has FREQ=) is kept verbatim once it parses; otherwise treat
    # the value as a natural-language keyword. Checking RRULE first avoids a
    # keyword like "weekly" matching inside "FREQ=WEEKLY;BYDAY=TU".
    if 'FREQ=' in value.upper():
        try:
            from dateutil.rrule import rrulestr
            rrulestr(value, dtstart=datetime.now())
            return value
        except Exception:
            return None
    return parse_recurrence(value)


def next_recurrence(recurrence, fire_at_iso):
    """Next fire time (ISO, naive local) for a recurring reminder, anchored to
    the original time-of-day pattern but always after *now* so a paused series
    doesn't replay a burst of missed occurrences. None when the series ends."""
    if not recurrence:
        return None
    try:
        from dateutil.rrule import rrulestr
        dt = datetime.fromisoformat(fire_at_iso)
        nxt = rrulestr(recurrence, dtstart=dt).after(datetime.now(), inc=False)
    except (ValueError, TypeError):
        return None
    return nxt.isoformat(timespec='seconds') if nxt else None


def check_reminders():
    """Runs every 60 seconds. Fires any reminders whose fire_at has passed."""
    now = datetime.now().isoformat(timespec='seconds')
    due = db.get_due_reminders(now)
    if due:
        log.info('Reminder check at %s: %d due', now, len(due))
    for reminder in due:
        try:
            _dispatch_reminder(reminder)
        except Exception:
            # One bad reminder (e.g. an SMS send error) must not abort the rest
            # or silently kill the job — log it and keep going.
            log.exception('Failed to dispatch reminder %s', reminder['id'])


def _dispatch_reminder(reminder):
    db.mark_reminder_fired(reminder['id'])
    user = db.get_user(reminder['user_id'])
    if reminder['notify_web']:
        sse.push_event(reminder['user_id'], 'reminder', {
            'id': reminder['id'],
            'message': reminder['message'],
            'fire_at': reminder['fire_at'],
        })
        # SSE only reaches open tabs; web push reaches the browser when none are.
        webpush.send_to_user(reminder['user_id'], '⏰ Reminder', reminder['message'])
    if reminder['notify_sms'] and user and user.get('phone_number'):
        import sms
        sms.send_sms(user, user['phone_number'],
                     f"⏰ Reminder: {reminder['message']}")
    # Recurring reminder: schedule the next occurrence as a fresh row so the
    # one that just fired stays visible in the pending/banner fallback.
    recurrence = reminder.get('recurrence')
    if recurrence:
        nxt = next_recurrence(recurrence, reminder['fire_at'])
        if nxt:
            db.create_reminder(reminder['user_id'], reminder['message'], nxt,
                               notify_sms=bool(reminder['notify_sms']),
                               notify_web=bool(reminder['notify_web']),
                               note_id=reminder['note_id'], recurrence=recurrence)
            log.info('Recurring reminder %s → next at %s', reminder['id'], nxt)


def run_calendar_sync():
    try:
        import calendar_sync
        calendar_sync.sync_all_users()
    except Exception:
        log.exception('Calendar sync failed')


def run_daily_digests():
    """Top of every hour: send the digest to anyone scheduled for this hour."""
    try:
        import digest
        digest.send_digests_for_hour(datetime.now().hour)
    except Exception:
        log.exception('Daily digest run failed')


def start():
    if scheduler.running:
        return
    scheduler.add_job(check_reminders, 'interval', seconds=60)
    scheduler.add_job(run_calendar_sync, 'interval', minutes=10)
    scheduler.add_job(run_daily_digests, 'cron', minute=0)
    scheduler.start()
    log.info('Scheduler started — reminders every 60s, calendar every 10m, '
             'digest hourly')
    atexit.register(lambda: scheduler.shutdown(wait=False))
