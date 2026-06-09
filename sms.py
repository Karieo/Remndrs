"""Twilio inbound SMS processing: command parser, note creation, replies."""

import logging
import os
import re
from datetime import datetime

import requests

import attachments as attachments_module
import database as db
import files
import sse

log = logging.getLogger(__name__)

MAX_SMS_LEN = 1600


def twilio_configured():
    return bool(os.getenv('TWILIO_ACCOUNT_SID') and os.getenv('TWILIO_AUTH_TOKEN'))


def validate_twilio_signature(request):
    if not twilio_configured():
        return False
    from twilio.request_validator import RequestValidator
    validator = RequestValidator(os.getenv('TWILIO_AUTH_TOKEN'))
    return validator.validate(
        request.url,
        request.form,
        request.headers.get('X-Twilio-Signature', ''))


def send_sms(user, to_number, body):
    if not twilio_configured():
        return
    from_number = (user or {}).get('twilio_number') or os.getenv('TWILIO_FROM_NUMBER')
    if not from_number or not to_number:
        return
    if len(body) > MAX_SMS_LEN:
        suffix = '… reply LIST for more'
        body = body[:MAX_SMS_LEN - len(suffix)] + suffix
    try:
        from twilio.rest import Client
        client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
        client.messages.create(body=body, from_=from_number, to=to_number)
    except Exception:
        log.exception('Failed to send SMS')


def _fmt_date(iso):
    try:
        return datetime.fromisoformat(iso).strftime('%b %-d')
    except (ValueError, TypeError):
        return (iso or '')[:10]


def _snippet(note, length=80):
    text = re.sub(r'\s+', ' ', note['content']).strip()
    if note['type'] == 'todo' and note.get('todos'):
        text = f"{text} (todo, {len(note['todos'])} items)"
    return text[:length]


def retrieve_by_tag(user, tag):
    notes = db.notes_by_tag(user['id'], tag, limit=3)
    tag_name = db.normalize_tag(tag)
    if not notes:
        return f'No notes tagged #{tag_name}.'
    lines = [f'#{tag_name} ({len(notes)} notes)', '']
    for n in notes:
        lines.append(f'{_fmt_date(n["created_at"])} · {_snippet(n)}')
        lines.append('')
    return '\n'.join(lines).strip()


def retrieve_by_search(user, keyword):
    notes = db.search_user_notes(user['id'], keyword, limit=3)
    if not notes:
        return f'No notes found for "{keyword}".'
    lines = [f'Search: "{keyword}" ({len(notes)} notes)', '']
    for n in notes:
        lines.append(f'{_fmt_date(n["created_at"])} · {_snippet(n)}')
        lines.append('')
    return '\n'.join(lines).strip()


def retrieve_recent(user):
    notes = db.recent_notes(user['id'], limit=5)
    if not notes:
        return 'No notes yet.'
    lines = ['Your 5 most recent notes:', '']
    for i, n in enumerate(notes, 1):
        lines.append(f'{i}. {_fmt_date(n["created_at"])} · {_snippet(n, 60)}')
    return '\n'.join(lines)


def create_reminder_from_text(user, text):
    """Parse 'REMIND ME [time expression] [message]' using dateparser."""
    try:
        from dateparser.search import search_dates
    except ImportError:
        return "Reminders aren't available right now."
    results = search_dates(text, settings={'PREFER_DATES_FROM': 'future'})
    if not results:
        return ('Couldn\'t understand that time. '
                'Try: "remind me June 15 at 3pm to [message]"')
    matched_text, fire_at = results[0]
    message = text.replace(matched_text, '', 1).strip()
    message = re.sub(r'^(to|that)\s+', '', message, flags=re.IGNORECASE).strip()
    if not message:
        message = 'Reminder'
    db.create_reminder(user['id'], message, fire_at.isoformat(timespec='seconds'),
                       notify_sms=True, notify_web=True)
    human = fire_at.strftime('%A, %B %-d at %-I:%M %p')
    return f'✓ Reminder set for {human}: "{message}"'


def extract_hashtags(text):
    return [t.upper() for t in re.findall(r'#([A-Za-z0-9_]+)', text or '')]


def create_note_from_sms(user, body, form):
    tags = ['SMS'] + extract_hashtags(body)
    feed = 'shared' if 'SHARED' in tags else 'private'
    note = db.create_note(user['id'], content=body.strip(), source='sms',
                          feed=feed, tags=list(dict.fromkeys(tags)))

    num_media = int(form.get('NumMedia', 0) or 0)
    if num_media > 0:
        links = download_sms_attachments(form, note['id'], user)
        if links:
            content = note['content'] + '\n\n' + '\n'.join(links)
            note = db.update_note(note['id'], content=content)

    filename = files.write_note_file(note, user['name'])
    note = db.update_note(note['id'], filename=filename)
    sse.push_note_event('note_created', note)
    return '✓ Saved'


def download_sms_attachments(form, note_id, user):
    links = []
    num = int(form.get('NumMedia', 0) or 0)
    auth = (os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
    for i in range(num):
        url = form.get(f'MediaUrl{i}')
        mime = form.get(f'MediaContentType{i}', 'application/octet-stream')
        if not url:
            continue
        try:
            resp = requests.get(url, auth=auth, timeout=30)
            resp.raise_for_status()
            ext = mime.split('/')[-1].replace('jpeg', 'jpg')
            saved = attachments_module.save(resp.content, f'attachment.{ext}',
                                            note_id, user, mime_type=mime)
            links.append(attachments_module.markdown_link(saved))
        except (requests.RequestException, ValueError) as e:
            log.warning('Could not download SMS attachment %s: %s', url, e)
    return links


def handle_inbound(form):
    """Process a verified inbound SMS webhook. Returns the reply body (or None)."""
    to_number = form.get('To', '')
    body = (form.get('Body') or '').strip()

    user = db.get_user_by_twilio_number(to_number)
    if not user:
        return "This number isn't configured."

    upper = body.upper()
    if upper.startswith('GET '):
        return retrieve_by_tag(user, body[4:].strip())
    if upper.startswith('FIND '):
        return retrieve_by_search(user, body[5:].strip())
    if upper == 'LIST' or upper.startswith('LIST '):
        return retrieve_recent(user)
    if upper.startswith('REMIND ME'):
        return create_reminder_from_text(user, body[len('REMIND ME'):].strip())
    return create_note_from_sms(user, body, form)
