"""Mailgun inbound email webhook processing."""

import hashlib
import hmac
import logging
import os
import re
from html.parser import HTMLParser

import attachments as attachments_module
import database as db
import files
import sse

log = logging.getLogger(__name__)


def mailgun_configured():
    return bool(os.getenv('MAILGUN_SIGNING_KEY'))


def mailgun_send_configured():
    return bool(os.getenv('MAILGUN_API_KEY') and os.getenv('MAILGUN_INBOUND_ADDRESS'))


def send_email(to_address, subject, text):
    """Send an outbound email via the Mailgun messages API.

    Uses the domain of MAILGUN_INBOUND_ADDRESS as the sending domain.
    Returns True on success.
    """
    if not mailgun_send_configured():
        return False
    inbound = os.getenv('MAILGUN_INBOUND_ADDRESS', '')
    domain = inbound.split('@', 1)[-1]
    import requests
    try:
        resp = requests.post(
            f'https://api.mailgun.net/v3/{domain}/messages',
            auth=('api', os.getenv('MAILGUN_API_KEY')),
            data={'from': f'Remndrs <{inbound}>',
                  'to': to_address,
                  'subject': subject,
                  'text': text},
            timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException:
        log.exception('Outbound email send failed')
        return False


def verify_mailgun_signature(token, timestamp, signature):
    signing_key = os.getenv('MAILGUN_SIGNING_KEY', '')
    if not signing_key:
        return False
    value = f'{timestamp}{token}'.encode('utf-8')
    expected = hmac.new(signing_key.encode('utf-8'), value, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or '')


class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)

    def get_text(self):
        return ' '.join(self.text).strip()


def strip_html(html: str) -> str:
    stripper = HTMLStripper()
    stripper.feed(html or '')
    return stripper.get_text()


_FWD_PREFIX = re.compile(r'^\s*((fwd?|re|fw)\s*:\s*)+', re.IGNORECASE)


def _reminder_request(subject, body):
    """Detect 'remind …' in the subject or the first body line of a
    forwarded email. Returns (fire_at_iso, message) or None."""
    import reminders
    candidates = [_FWD_PREFIX.sub('', subject or '')]
    first_line = next((l.strip() for l in (body or '').split('\n') if l.strip()), '')
    if not first_line.startswith(('---', '>', 'From:')):
        candidates.append(first_line)
    for text in candidates:
        # Must lead with the keyword ("Remind me…", "Reminder: …") or say
        # "remind me" explicitly — mentioning the word in passing doesn't count.
        if not (re.match(r'\s*remind(er)?\b', text, re.IGNORECASE)
                or re.search(r'\bremind me\b', text, re.IGNORECASE)):
            continue
        parsed = reminders.parse_remind_text(text)
        if parsed:
            return parsed
    return None


_TAG_LINE = re.compile(r'^\s*tags?\s*:\s*(.+?)\s*$', re.IGNORECASE)
_HASHTAG_ONLY_LINE = re.compile(r'^\s*(#[A-Za-z0-9_]+[\s,]*)+\s*$')


def _extract_tag_lines(body):
    """Pull tag declarations out of the email body.

    Two forms, each consumed (removed from the note content):
      Tags: groceries, costco        — a dedicated tags line
      #groceries #costco             — a line consisting only of hashtags
    Returns (cleaned_body, tags).
    """
    tags, kept = [], []
    for line in (body or '').split('\n'):
        m = _TAG_LINE.match(line)
        if m:
            tags += [t.strip().lstrip('#').upper().replace(' ', '_')
                     for t in re.split(r'[,;]', m.group(1)) if t.strip()]
            continue
        if _HASHTAG_ONLY_LINE.match(line):
            tags += [t.upper() for t in re.findall(r'#([A-Za-z0-9_]+)', line)]
            continue
        kept.append(line)
    return '\n'.join(kept).strip(), tags


def _extract_tags(subject, body):
    tags = ['EMAIL']
    tags += [t.upper() for t in re.findall(r'#([A-Za-z0-9_]+)', f'{subject}\n{body}')]
    # Subject prefixes like "[IDEAS]" or "(PERSONAL)" become tags
    for m in re.findall(r'^[\[(]([A-Za-z0-9_ ]+)[\])]', subject or ''):
        name = m.strip().upper()
        if name and name != 'SHARED':
            tags.append(name.replace(' ', '_'))
    return list(dict.fromkeys(tags))


def process_inbound(form, file_storage_items):
    """Process a verified Mailgun webhook. Returns True if a note was created."""
    recipient = (form.get('recipient') or '').strip()
    user = db.get_user_by_email(recipient) if recipient else None
    if not user:
        sender = form.get('from', '')
        log.warning('Inbound email to %s (from %s) matched no user — discarded',
                    recipient, sender)
        return False

    subject = (form.get('subject') or '').strip()
    body = (form.get('body-plain') or '').strip()
    if not body:
        body = strip_html(form.get('body-html') or '')

    body, declared_tags = _extract_tag_lines(body)
    content = f'**{subject}**\n\n{body}' if subject else body
    tags = _extract_tags(subject, body)
    tags += [t for t in declared_tags if t not in tags]
    # [shared] in the subject or a declared SHARED tag routes to the shared feed
    feed = 'shared' if ('[shared]' in subject.lower() or 'SHARED' in tags) else 'private'
    if feed == 'shared' and 'SHARED' not in tags:
        tags.append('SHARED')

    reminder_request = _reminder_request(subject, body)
    if reminder_request and 'REMINDER' not in tags:
        tags.append('REMINDER')

    note = db.create_note(user['id'], content=content.strip(), source='email',
                          feed=feed, tags=tags)

    if reminder_request:
        fire_at, message = reminder_request
        if not message:
            message = _FWD_PREFIX.sub('', subject).strip() or 'Reminder'
        db.create_reminder(user['id'], message, fire_at,
                           notify_sms=True, notify_web=True, note_id=note['id'])
        log.info('Email reminder set for %s: %r', fire_at, message)
        sender = form.get('from', '')
        if sender and mailgun_send_configured():
            from datetime import datetime
            human = datetime.fromisoformat(fire_at).strftime('%A, %B %-d at %-I:%M %p')
            send_email(sender, f'✓ Reminder set for {human}',
                       f'"{message}"\n\nThe forwarded email is saved in your feed.')

    links = []
    for storage in file_storage_items:
        if not storage or not storage.filename:
            continue
        try:
            data = storage.read()
            saved = attachments_module.save(data, storage.filename, note['id'], user,
                                            mime_type=storage.mimetype)
            links.append(attachments_module.markdown_link(saved))
        except (ValueError, OSError) as e:
            log.warning('Skipped email attachment %s: %s', storage.filename, e)
    if links:
        note = db.update_note(note['id'], content=note['content'] + '\n\n' + '\n'.join(links))

    filename = files.write_note_file(note, user['name'])
    note = db.update_note(note['id'], filename=filename)
    sse.push_note_event('note_created', note)
    return True
