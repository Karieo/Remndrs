"""APScheduler background jobs: reminder dispatch + calendar sync.
Also the shared natural-language reminder parser used by SMS and email."""

import atexit
import logging
import re
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

import database as db
import sse

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
    if reminder['notify_sms'] and user and user.get('phone_number'):
        import sms
        sms.send_sms(user, user['phone_number'],
                     f"⏰ Reminder: {reminder['message']}")


def run_calendar_sync():
    try:
        import calendar_sync
        calendar_sync.sync_all_users()
    except Exception:
        log.exception('Calendar sync failed')


def start():
    if scheduler.running:
        return
    scheduler.add_job(check_reminders, 'interval', seconds=60)
    scheduler.add_job(run_calendar_sync, 'interval', minutes=10)
    scheduler.start()
    log.info('Scheduler started — reminder dispatch every 60s, calendar sync every 10m')
    atexit.register(lambda: scheduler.shutdown(wait=False))
