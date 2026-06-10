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

    content = f'**{subject}**\n\n{body}' if subject else body
    feed = 'shared' if '[shared]' in subject.lower() else 'private'
    tags = _extract_tags(subject, body)
    if feed == 'shared' and 'SHARED' not in tags:
        tags.append('SHARED')

    note = db.create_note(user['id'], content=content.strip(), source='email',
                          feed=feed, tags=tags)

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
