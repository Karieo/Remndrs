"""Telegram bot channel: inbound message handling, command parsing, replies.

Telegram needs no carrier registration — set TELEGRAM_BOT_TOKEN (from @BotFather)
and register the webhook once (Settings → Integrations → Connect). Messages your
bot receives become notes, reusing the same GET/FIND/LIST/REMIND ME command
grammar as SMS.
"""

import logging
import os

import requests

import database as db
import files
import sms
import sse

log = logging.getLogger(__name__)

API = 'https://api.telegram.org/bot{token}/{method}'


def telegram_configured():
    return bool(os.getenv('TELEGRAM_BOT_TOKEN'))


def _call(method, **payload):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        return {'ok': False, 'description': 'No bot token'}
    try:
        resp = requests.post(API.format(token=token, method=method),
                             json=payload, timeout=15)
        return resp.json()
    except requests.RequestException as e:
        log.warning('Telegram %s failed: %s', method, e)
        return {'ok': False, 'description': str(e)}


def get_me():
    return _call('getMe')


def webhook_info():
    return _call('getWebhookInfo')


def set_webhook(public_url, secret):
    """Point the bot at our /webhooks/telegram, guarded by a secret token."""
    url = public_url.rstrip('/') + '/webhooks/telegram'
    return _call('setWebhook', url=url, secret_token=secret,
                 allowed_updates=['message', 'edited_message'])


def verify_secret(request):
    """Telegram echoes the secret we set on the webhook in this header."""
    expected = os.getenv('TELEGRAM_WEBHOOK_SECRET')
    if not expected:
        return False
    return request.headers.get('X-Telegram-Bot-Api-Secret-Token', '') == expected


def send_message(chat_id, text):
    _call('sendMessage', chat_id=chat_id, text=text)


def _help_text():
    return ('I save what you send me as a note. Commands:\n'
            '• just type — saves a note (add #tags inline)\n'
            '• GET #tag — your latest notes with that tag\n'
            '• FIND words — search your notes\n'
            '• LIST — your 5 most recent\n'
            '• REMIND ME tomorrow 9am to … — set a reminder')


def create_note_from_telegram(user, text):
    tags = ['TELEGRAM'] + sms.extract_hashtags(text)
    feed = 'shared' if 'SHARED' in tags else 'private'
    note = db.create_note(user['id'], content=text.strip(), source='telegram',
                          feed=feed, tags=list(dict.fromkeys(tags)))
    filename = files.write_note_file(note, user['name'])
    note = db.update_note(note['id'], filename=filename)
    sse.push_note_event('note_created', note)
    return '✓ Saved'


def _dispatch(user, text):
    upper = text.upper()
    if upper in ('/START', '/HELP', 'HELP'):
        return _help_text()
    if upper.startswith('GET '):
        return sms.retrieve_by_tag(user, text[4:].strip())
    if upper.startswith('FIND '):
        return sms.retrieve_by_search(user, text[5:].strip())
    if upper == 'LIST' or upper.startswith('LIST '):
        return sms.retrieve_recent(user)
    if upper.startswith('REMIND ME'):
        return sms.create_reminder_from_text(user, text[len('REMIND ME'):].strip())
    return create_note_from_telegram(user, text)


def handle_update(update):
    """Process one webhook update. Replies are sent via the API, not the response."""
    message = update.get('message') or update.get('edited_message')
    if not message:
        return
    chat = message.get('chat', {})
    chat_id = str(chat.get('id', ''))
    text = (message.get('text') or message.get('caption') or '').strip()
    if not chat_id or not text:
        return

    user = db.get_user_by_telegram_chat_id(chat_id)
    if not user:
        name = chat.get('first_name', 'there')
        send_message(chat_id,
                     f"👋 Hi {name}! This chat isn't linked to Remndrs yet.\n\n"
                     "In Remndrs, open ⚙ Settings → People and paste this into "
                     f"\"Telegram chat ID\":\n\n{chat_id}\n\n"
                     "Then send me a note and I'll save it.")
        return

    reply = _dispatch(user, text)
    if reply:
        send_message(chat_id, reply)
