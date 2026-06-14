"""Daily digest: a once-a-day summary of the last 24h of notes and the day's
reminders, delivered by email and/or SMS at a per-user local hour.

Scheduled from reminders.py (a cron job at the top of every hour). Self-
disabling: a user with no digest_hour is skipped, and delivery uses whichever
channels are configured (Mailgun for email, Twilio for SMS).
"""

import logging
from datetime import date, datetime, timedelta

import database as db

log = logging.getLogger(__name__)

MAX_ITEMS = 10


def _first_line(text, limit=80):
    line = (text or '').strip().split('\n', 1)[0]
    return line[:limit] + ('…' if len(line) > limit else '')


def build_digest(user):
    """Return (subject, body) for the user's digest, or None if there's nothing
    worth sending (no new notes and no reminders today)."""
    since = (datetime.now() - timedelta(hours=24)).isoformat(timespec='seconds')
    tomorrow = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                + timedelta(days=1)).isoformat(timespec='seconds')
    notes = db.notes_since(user['id'], since)
    rems = db.reminders_today(user['id'], tomorrow)
    if not notes and not rems:
        return None

    lines = [f"Good day, {user['name']}. Here's your Remndrs digest.", '']
    if rems:
        lines.append(f"⏰ Reminders ({len(rems)}):")
        for r in rems:
            when = r['fire_at'][11:16]  # HH:MM
            lines.append(f"  • {when} — {r['message']}")
        lines.append('')
    if notes:
        lines.append(f"📝 Notes in the last 24h ({len(notes)}):")
        for n in notes[:MAX_ITEMS]:
            lines.append(f"  • {_first_line(n['content'])}")
        if len(notes) > MAX_ITEMS:
            lines.append(f"  …and {len(notes) - MAX_ITEMS} more.")
    return 'Your Remndrs daily digest', '\n'.join(lines).strip()


def _deliver(user, subject, body):
    """Send via every configured channel. Returns True if at least one sent."""
    sent = False
    if user.get('email'):
        try:
            import email_inbound
            if email_inbound.mailgun_send_configured():
                email_inbound.send_email(user['email'], subject, body)
                sent = True
        except Exception:
            log.exception('Digest email failed for %s', user['id'])
    if user.get('phone_number'):
        try:
            import sms
            if sms.twilio_configured():
                sms.send_sms(user, user['phone_number'], body)
                sent = True
        except Exception:
            log.exception('Digest SMS failed for %s', user['id'])
    return sent


def send_digests_for_hour(hour, today=None):
    """Send the digest to every user whose digest_hour matches `hour`, once per
    day (guarded by digest_last_sent so a restart within the hour won't repeat)."""
    today = today or date.today().isoformat()
    for user in db.users_for_digest_hour(hour):
        if user.get('digest_last_sent') == today:
            continue
        built = build_digest(user)
        if built and _deliver(user, *built):
            log.info('Sent daily digest to %s', user['name'])
        db.mark_digest_sent(user['id'], today)  # mark even when empty: one check/day
