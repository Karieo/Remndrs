"""APScheduler background jobs: reminder dispatch + calendar sync."""

import atexit
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

import database as db
import sse

log = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def check_reminders():
    """Runs every 60 seconds. Fires any reminders whose fire_at has passed."""
    now = datetime.now().isoformat(timespec='seconds')
    for reminder in db.get_due_reminders(now):
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
    atexit.register(lambda: scheduler.shutdown(wait=False))
