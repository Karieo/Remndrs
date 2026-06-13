"""Remndrs — Flask server: auth, all API routes, webhooks, SSE stream."""

import hashlib
import json
import logging
import os
import re
import secrets
import socket
import tempfile
import time
import uuid
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()


def apply_timezone():
    """Pin the process timezone from the TIMEZONE setting.

    Remndrs stores naive local wall-clock times everywhere (created_at, reminder
    fire_at, calendar windows, date search), so "local" means whatever timezone
    the host's clock is set to. When the host is on the wrong zone (a Pi, a
    container, or a cloud box defaulting to UTC), every timestamp lands hours
    off — notes appear in the future, reminders fire early. Setting TIMEZONE
    (an IANA name like "America/New_York") makes the app use that zone for
    datetime.now() regardless of the host, so the install isn't at the mercy of
    the system clock's zone. Unset → keep the host zone (the prior behaviour)."""
    tz = os.getenv('TIMEZONE', '').strip()
    if not tz:
        return
    os.environ['TZ'] = tz
    try:
        time.tzset()  # Unix only; Windows keeps the system zone.
    except AttributeError:
        logging.getLogger('remndrs').warning(
            'TIMEZONE set but time.tzset() is unavailable on this OS')


apply_timezone()

import bcrypt
import requests as http
from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, send_file, session)
from werkzeug.middleware.proxy_fix import ProxyFix

import attachments as attachments_module
import database as db
import email_inbound
import files
import reminders
import sms
import sse
import telegram
import mcp_server
import voice

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('remndrs')

app = Flask(__name__)

# Behind the Cloudflare tunnel (or any reverse proxy) the request reaches us
# over plain http on localhost, so Flask would reconstruct request.url with the
# wrong scheme/host. Twilio and Mailgun sign the *public* https URL, so without
# this their signature checks fail with a 403 and inbound notes silently vanish.
# Trust the X-Forwarded-Proto/Host/For headers cloudflared sets; x_for makes
# request.remote_addr the real visitor IP (needed for login throttling + logs).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Lax blocks the session cookie on cross-site POSTs (CSRF) without breaking
# normal navigation. Secure stays off because the app is also used over plain
# http on the LAN (http://<host>.local:3000); Cloudflare enforces https publicly.
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Caps any request body (uploads included) — big enough for photos and voice
# memos, small enough that strangers can't fill the disk.
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

_secret = os.getenv('SESSION_SECRET')
if not _secret:
    _secret = secrets.token_hex(32)
    log.warning('SESSION_SECRET not set — generated a random one '
                '(sessions will not survive restarts)')
app.secret_key = _secret
app.permanent_session_lifetime = timedelta(days=7)

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOADS_DIR, exist_ok=True)


# ── Version ──────────────────────────────────────────────
# VERSION is bumped by hand; the git commit + date below auto-update on every
# `git pull`, so the login/settings stamp tells you at a glance whether a deploy
# actually landed. Surfaced in the UI, at /api/version, and in the startup log.
VERSION = '0.2.0'
_APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _git_build():
    import subprocess
    opts = {'cwd': _APP_DIR, 'stderr': subprocess.DEVNULL, 'timeout': 3}
    try:
        sha = subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'], **opts).decode().strip()
        date = subprocess.check_output(
            ['git', 'log', '-1', '--format=%cd', '--date=short'], **opts).decode().strip()
        return sha, date
    except Exception:
        return None, None


_GIT_SHA, _GIT_DATE = _git_build()
VERSION_LABEL = (f'v{VERSION} · {_GIT_SHA} · {_GIT_DATE}'
                 if _GIT_SHA else f'v{VERSION}')
log.info('Remndrs %s starting', VERSION_LABEL)
mcp_server.SERVER_VERSION = VERSION


@app.context_processor
def inject_version():
    return {'app_version': VERSION_LABEL}


# ── Bootstrap ────────────────────────────────────────────

def seed_owner():
    if db.count_users() > 0:
        return
    name = os.getenv('OWNER_NAME', 'Owner')
    password = os.getenv('OWNER_PASSWORD', 'changeme')
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db.create_user(name, password_hash,
                   phone_number=os.getenv('OWNER_PHONE_NUMBER') or None,
                   role='owner')
    log.info('Seeded owner account "%s"', name)


db.init_db()
seed_owner()


# ── Auth ─────────────────────────────────────────────────

PUBLIC_PATHS = ('/login', '/api/auth/login', '/api/auth/token', '/api/version',
                '/webhooks/', '/static/', '/mcp')


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


# Per-IP failed-login throttle: after _THROTTLE_MAX failures within
# _THROTTLE_WINDOW, that IP gets 429s on the auth endpoints until the window
# rolls. In-memory on purpose — a restart clearing it is fine for a home app.
_AUTH_FAILURES = {}
_THROTTLE_WINDOW = 15 * 60
_THROTTLE_MAX = 8


def _auth_throttled(ip):
    now = time.time()
    fresh = [t for t in _AUTH_FAILURES.get(ip, []) if now - t < _THROTTLE_WINDOW]
    if fresh:
        _AUTH_FAILURES[ip] = fresh
    else:
        _AUTH_FAILURES.pop(ip, None)
    return len(fresh) >= _THROTTLE_MAX


def _record_auth_failure(ip):
    _AUTH_FAILURES.setdefault(ip, []).append(time.time())
    log.warning('Failed login attempt from %s', ip)


def _user_from_bearer():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    return db.get_user_by_token_hash(_hash_token(auth[7:].strip()))


@app.before_request
def require_login():
    path = request.path
    if any(path == p or path.startswith(p) for p in PUBLIC_PATHS):
        return None
    if session.get('user_id'):
        return None
    user = _user_from_bearer()
    if user:
        # Request-scoped identity: handlers read session['user_id'], but no
        # cookie is sent back to the token client.
        session['user_id'] = user['id']
        session.modified = False
        return None
    if path.startswith('/api/'):
        return jsonify({'error': 'Unauthorized'}), 401
    return redirect('/login')


def current_user():
    return db.get_user(session.get('user_id'))


@app.route('/api/version')
def api_version():
    return jsonify({'version': VERSION, 'commit': _GIT_SHA,
                    'date': _GIT_DATE, 'label': VERSION_LABEL})


@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    if _auth_throttled(request.remote_addr):
        return jsonify({'error': 'Too many attempts — try again later'}), 429
    data = request.get_json(silent=True) or request.form
    login = (data.get('login') or data.get('email_or_name') or '').strip()
    password = data.get('password') or ''
    user = db.get_user_by_login(login)
    if not user or not bcrypt.checkpw(password.encode(),
                                      user['password_hash'].encode()):
        _record_auth_failure(request.remote_addr)
        return jsonify({'error': 'Invalid credentials'}), 401
    _AUTH_FAILURES.pop(request.remote_addr, None)
    session.permanent = True
    session['user_id'] = user['id']
    return jsonify({'success': True,
                    'user': {'id': user['id'], 'name': user['name'],
                             'role': user['role']}})


@app.route('/api/auth/token', methods=['POST'])
def api_create_token():
    """Issue a long-lived bearer token for mobile clients."""
    if _auth_throttled(request.remote_addr):
        return jsonify({'error': 'Too many attempts — try again later'}), 429
    data = request.get_json(silent=True) or {}
    login = (data.get('login') or '').strip()
    password = data.get('password') or ''
    user = db.get_user_by_login(login)
    if not user or not bcrypt.checkpw(password.encode(),
                                      user['password_hash'].encode()):
        _record_auth_failure(request.remote_addr)
        return jsonify({'error': 'Invalid credentials'}), 401
    _AUTH_FAILURES.pop(request.remote_addr, None)
    token = secrets.token_urlsafe(32)
    db.create_api_token(user['id'], _hash_token(token),
                        device_name=data.get('device_name'))
    return jsonify({'token': token,
                    'user': {'id': user['id'], 'name': user['name'],
                             'role': user['role']}}), 201


@app.route('/api/auth/token', methods=['DELETE'])
def api_revoke_token():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        db.delete_api_token_by_hash(_hash_token(auth[7:].strip()))
    return jsonify({'success': True})


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})


# ── Pages ────────────────────────────────────────────────

@app.route('/')
def index():
    user = current_user()
    return render_template('index.html', user=user,
                           voice_enabled=voice.openai_configured())


# ── Notes ────────────────────────────────────────────────

def _can_see(note, user_id):
    return note and (note['user_id'] == user_id or note['feed'] == 'shared')


def _persist_note_file(note):
    owner = db.get_user(note['user_id'])
    filename = files.write_note_file(note, owner['name'])
    if filename != note.get('filename'):
        note = db.update_note(note['id'], filename=filename)
    return note


@app.route('/api/notes')
def api_list_notes():
    # feed=archived is the archived view: all archived notes the user can
    # see, both feeds together. Every other feed value excludes archived.
    feed = request.args.get('feed')
    archived = feed == 'archived'
    notes = db.list_notes(session['user_id'],
                          tag=request.args.get('tag'),
                          search=request.args.get('search'),
                          source=request.args.get('source'),
                          feed=None if archived else feed,
                          archived=archived)
    return jsonify(notes)


@app.route('/api/notes/<note_id>')
def api_get_note(note_id):
    note = db.get_note(note_id)
    if not _can_see(note, session['user_id']):
        return jsonify({'error': 'Not found'}), 404
    return jsonify(note)


@app.route('/api/notes', methods=['POST'])
def api_create_note():
    data = request.get_json(silent=True) or {}
    note = db.create_note(
        session['user_id'],
        content=data.get('content', ''),
        note_type=data.get('type', 'note'),
        feed=data.get('feed', 'private'),
        source=data.get('source', 'web'),
        pinned=data.get('pinned', False),
        tags=data.get('tags'),
        todos=data.get('todos'))
    note = _persist_note_file(note)
    sse.push_note_event('note_created', note)
    return jsonify(note), 201


@app.route('/api/notes/<note_id>', methods=['PATCH'])
def api_update_note(note_id):
    existing = db.get_note(note_id)
    if not _can_see(existing, session['user_id']):
        return jsonify({'error': 'Not found'}), 404
    data = request.get_json(silent=True) or {}

    fields = {k: data[k] for k in ('content', 'feed', 'type', 'pinned', 'archived')
              if k in data}
    note = db.update_note(note_id, **fields) if fields else existing
    if 'tags' in data:
        db.set_note_tags(note_id, data['tags'], created_by=session['user_id'])
    if 'todos' in data:
        db.replace_todos(note_id, data['todos'])
    note = db.get_note(note_id)

    owner = db.get_user(note['user_id'])
    if 'feed' in fields and fields['feed'] != existing['feed']:
        files.move_note_file(existing, owner['name'], existing['feed'])
        note = db.update_note(note_id, filename=None)
    note = _persist_note_file(note)
    sse.push_note_event('note_updated', note)
    return jsonify(note)


@app.route('/api/notes/<note_id>', methods=['DELETE'])
def api_delete_note(note_id):
    note = db.get_note(note_id)
    if not _can_see(note, session['user_id']):
        return jsonify({'error': 'Not found'}), 404
    owner = db.get_user(note['user_id'])
    files.delete_note_file(note, owner['name'])
    db.delete_note(note_id)
    sse.push_note_event('note_deleted', {'id': note_id, 'feed': note['feed'],
                                         'user_id': note['user_id']})
    return jsonify({'success': True})


# ── Settings (owner-configurable integrations) ───────────

# Keys editable from the settings panel. True = secret (never echoed back).
SETTINGS_KEYS = {
    'TWILIO_ACCOUNT_SID': False,
    'TWILIO_AUTH_TOKEN': True,
    'OWNER_PHONE_NUMBER': False,
    'OPENAI_API_KEY': True,
    'MAILGUN_API_KEY': True,
    'MAILGUN_SIGNING_KEY': True,
    'MAILGUN_INBOUND_ADDRESS': False,
    'CALDAV_USERNAME': False,
    'CALDAV_PASSWORD': True,
    'TELEGRAM_BOT_TOKEN': True,
    'PUBLIC_URL': False,
    'TIMEZONE': False,
}

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')


def _write_env(updates):
    """Persist key=value pairs into .env (replace or append) and apply live."""
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            lines = f.read().splitlines()
    for key, value in updates.items():
        os.environ[key] = value
        replaced = False
        for i, line in enumerate(lines):
            if line.startswith(f'{key}='):
                lines[i] = f'{key}={value}'
                replaced = True
                break
        if not replaced:
            lines.append(f'{key}={value}')
    with open(ENV_PATH, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def _require_owner():
    user = current_user()
    return user if user and user['role'] == 'owner' else None


@app.route('/api/settings')
def api_get_settings():
    if not _require_owner():
        return jsonify({'error': 'Owner only'}), 403
    values = {}
    for key, secret in SETTINGS_KEYS.items():
        value = os.getenv(key, '')
        values[key] = {'set': bool(value), 'value': '' if secret else value}
    values['status'] = {
        'sms': sms.twilio_configured(),
        'voice_transcription': voice.openai_configured(),
        'email_in': email_inbound.mailgun_configured(),
        'email_out': email_inbound.mailgun_send_configured(),
        'calendar': bool(os.getenv('CALDAV_USERNAME') and os.getenv('CALDAV_PASSWORD')),
        'telegram': telegram.telegram_configured(),
        'claude': _claude_connected(session['user_id']),
    }
    return jsonify(values)


CLAUDE_DEVICE_NAME = 'Claude (MCP)'


def _claude_connected(user_id):
    return any(t['device_name'] == CLAUDE_DEVICE_NAME
               for t in db.list_api_tokens(user_id))


@app.route('/api/integrations/status')
def api_integrations_status():
    """Which capture channels are actually wired up. Unlike /api/settings this
    is readable by every signed-in user so the channel rail can hide the
    channels nobody can use yet."""
    return jsonify({
        'sms': sms.twilio_configured(),
        'telegram': telegram.telegram_configured(),
        'voice': voice.openai_configured(),
        'email': email_inbound.mailgun_configured(),
        'cal': bool(os.getenv('CALDAV_USERNAME') and os.getenv('CALDAV_PASSWORD')),
        'claude': _claude_connected(session['user_id']),
    })


@app.route('/api/settings', methods=['PATCH'])
def api_update_settings():
    if not _require_owner():
        return jsonify({'error': 'Owner only'}), 403
    data = request.get_json(silent=True) or {}
    updates = {k: str(v).strip() for k, v in data.items()
               if k in SETTINGS_KEYS and str(v).strip() != ''}
    if updates:
        _write_env(updates)
        if 'TIMEZONE' in updates:
            apply_timezone()  # take effect now, not just on restart
        log.info('Settings updated: %s', ', '.join(updates))
    return jsonify({'success': True, 'updated': sorted(updates)})


@app.route('/api/settings/test/<service>', methods=['POST'])
def api_test_settings(service):
    """Live connection test for each integration."""
    if not _require_owner():
        return jsonify({'error': 'Owner only'}), 403
    try:
        if service == 'twilio':
            if not sms.twilio_configured():
                return jsonify({'ok': False, 'detail': 'SID and auth token required'})
            from twilio.rest import Client
            account = Client(os.getenv('TWILIO_ACCOUNT_SID'),
                             os.getenv('TWILIO_AUTH_TOKEN')) \
                .api.accounts(os.getenv('TWILIO_ACCOUNT_SID')).fetch()
            return jsonify({'ok': True, 'detail': f'Connected: {account.friendly_name}'})

        if service == 'openai':
            if not voice.openai_configured():
                return jsonify({'ok': False, 'detail': 'API key required'})
            import openai
            openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY')).models.retrieve('whisper-1')
            return jsonify({'ok': True, 'detail': 'Key valid — Whisper available'})

        if service == 'mailgun':
            if not os.getenv('MAILGUN_API_KEY') or not os.getenv('MAILGUN_INBOUND_ADDRESS'):
                return jsonify({'ok': False, 'detail': 'API key and inbound address required'})
            domain = os.getenv('MAILGUN_INBOUND_ADDRESS').split('@', 1)[-1]
            resp = http.get(f'https://api.mailgun.net/v3/domains/{domain}',
                            auth=('api', os.getenv('MAILGUN_API_KEY')), timeout=15)
            if resp.status_code == 200:
                state = resp.json().get('domain', {}).get('state', 'unknown')
                return jsonify({'ok': True, 'detail': f'Domain {domain}: {state}'})
            return jsonify({'ok': False, 'detail': f'Mailgun says {resp.status_code} for {domain}'})

        if service == 'telegram':
            if not telegram.telegram_configured():
                return jsonify({'ok': False, 'detail': 'Bot token required'})
            me = telegram.get_me()
            if not me.get('ok'):
                return jsonify({'ok': False,
                                'detail': me.get('description', 'Invalid bot token')})
            username = me['result'].get('username', '?')
            hooked = bool(telegram.webhook_info().get('result', {}).get('url'))
            return jsonify({'ok': True, 'detail': f'@{username} — '
                            + ('webhook connected' if hooked
                               else 'token valid, now click Connect')})

        if service == 'caldav':
            import calendar_sync
            calendars = calendar_sync.discover_calendars(session['user_id'])
            if calendars:
                return jsonify({'ok': True,
                                'detail': f'Found {len(calendars)} calendar(s)'})
            return jsonify({'ok': False,
                            'detail': 'Connected but no calendars — check the app-specific password'})

        if service == 'claude':
            if not os.getenv('PUBLIC_URL', '').strip():
                return jsonify({'ok': False,
                                'detail': 'Set your Public URL in the Webhooks tab first'})
            if _claude_connected(session['user_id']):
                return jsonify({'ok': True,
                                'detail': 'Connector token active — endpoint ready'})
            return jsonify({'ok': False, 'detail': 'No token yet — click Connect'})

        return jsonify({'error': 'Unknown service'}), 400
    except Exception as e:
        return jsonify({'ok': False, 'detail': str(e)[:200]})


@app.route('/api/settings/telegram/connect', methods=['POST'])
def api_telegram_connect():
    """Register the bot's webhook with Telegram (owner only, one-time setup)."""
    if not _require_owner():
        return jsonify({'error': 'Owner only'}), 403
    if not telegram.telegram_configured():
        return jsonify({'ok': False, 'detail': 'Save your bot token first'})
    public = os.getenv('PUBLIC_URL', '').strip()
    if not public:
        return jsonify({'ok': False,
                        'detail': 'Set your Public URL in the Webhooks tab first'})
    secret = os.getenv('TELEGRAM_WEBHOOK_SECRET')
    if not secret:
        secret = secrets.token_urlsafe(24)
        _write_env({'TELEGRAM_WEBHOOK_SECRET': secret})
    result = telegram.set_webhook(public, secret)
    if result.get('ok'):
        return jsonify({'ok': True,
                        'detail': 'Connected — text your bot to capture notes'})
    return jsonify({'ok': False, 'detail': result.get('description', 'setWebhook failed')})


@app.route('/api/settings/claude/connect', methods=['POST'])
def api_claude_connect():
    """Mint (or rotate) the Claude MCP capability URL. The raw token is stored
    hashed, so the URL can only be shown once — reconnecting revokes the old
    token and mints a fresh one. Owner-only v1, like the whole Integrations tab."""
    user = _require_owner()
    if not user:
        return jsonify({'error': 'Owner only'}), 403
    public = os.getenv('PUBLIC_URL', '').strip().rstrip('/')
    if not public:
        return jsonify({'ok': False,
                        'detail': 'Set your Public URL in the Webhooks tab first'})
    db.delete_api_tokens_by_device(user['id'], CLAUDE_DEVICE_NAME)
    token = secrets.token_urlsafe(32)
    db.create_api_token(user['id'], _hash_token(token),
                        device_name=CLAUDE_DEVICE_NAME)
    log.info('Claude MCP connector token minted for %s', user['name'])
    return jsonify({'ok': True,
                    'detail': 'Connector URL created — copy it now, it is shown only once',
                    'url': f'{public}/mcp/{token}'})


# ── Users ────────────────────────────────────────────────

@app.route('/api/users')
def api_list_users():
    """Other people in the system — for the share-with picker."""
    return jsonify([{'id': u['id'], 'name': u['name']} for u in db.list_users()])


@app.route('/api/users/me')
def api_get_me():
    user = current_user()
    return jsonify({k: user.get(k) for k in
                    ('id', 'name', 'role', 'email', 'phone_number', 'twilio_number',
                     'telegram_chat_id')})


@app.route('/api/users/me', methods=['PATCH'])
def api_update_me():
    data = request.get_json(silent=True) or {}
    user = db.update_user_contact(session['user_id'],
                                  email=data.get('email'),
                                  phone_number=data.get('phone_number'),
                                  twilio_number=data.get('twilio_number'),
                                  telegram_chat_id=data.get('telegram_chat_id'))
    return jsonify({k: user.get(k) for k in
                    ('id', 'name', 'role', 'email', 'phone_number', 'twilio_number',
                     'telegram_chat_id')})


@app.route('/api/users', methods=['POST'])
def api_create_user():
    """Add a person (owner only) — replaces the old python one-liner."""
    if not _require_owner():
        return jsonify({'error': 'Owner only'}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    password = data.get('password') or ''
    if not name or not password:
        return jsonify({'error': 'name and password are required'}), 400
    if db.get_user_by_login(name):
        return jsonify({'error': 'That name is taken'}), 400
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = db.create_user(name, password_hash,
                          email=(data.get('email') or '').strip() or None,
                          phone_number=(data.get('phone_number') or '').strip() or None)
    return jsonify({'id': user['id'], 'name': user['name']}), 201


@app.route('/api/notes/<note_id>/share', methods=['POST'])
def api_share_note(note_id):
    """Share a note with a person: moves it to the shared feed with
    sender→recipient attribution and an optional message."""
    note = db.get_note(note_id)
    if not _can_see(note, session['user_id']):
        return jsonify({'error': 'Not found'}), 404
    data = request.get_json(silent=True) or {}
    recipient = db.get_user(data.get('recipient_id', ''))
    if not recipient:
        return jsonify({'error': 'Recipient not found'}), 404
    if recipient['id'] == session['user_id']:
        return jsonify({'error': "That's you"}), 400

    db.create_share(note_id, session['user_id'], recipient['id'],
                    message=(data.get('message') or '').strip() or None)
    owner = db.get_user(note['user_id'])
    if note['feed'] != 'shared':
        files.move_note_file(note, owner['name'], note['feed'])
        db.update_note(note_id, feed='shared', filename=None)
    note = db.get_note(note_id)
    note = _persist_note_file(note)
    sse.push_note_event('note_updated', note)
    return jsonify(note), 201


@app.route('/api/notes/<note_id>/replies', methods=['POST'])
def api_reply_to_note(note_id):
    note = db.get_note(note_id)
    if not _can_see(note, session['user_id']):
        return jsonify({'error': 'Not found'}), 404
    if note['feed'] != 'shared':
        return jsonify({'error': 'Replies are for shared notes'}), 400
    text = ((request.get_json(silent=True) or {}).get('text') or '').strip()
    if not text:
        return jsonify({'error': 'text is required'}), 400

    reply = db.add_reply(note_id, session['user_id'], text)
    note = db.get_note(note_id)
    note = _persist_note_file(note)
    sse.push_note_event('note_updated', note)
    return jsonify(reply), 201


@app.route('/api/notes/<note_id>/send', methods=['POST'])
def api_send_note(note_id):
    """Push a note back out via SMS or email ("send anywhere")."""
    note = db.get_note(note_id)
    if not _can_see(note, session['user_id']):
        return jsonify({'error': 'Not found'}), 404
    data = request.get_json(silent=True) or {}
    channel = data.get('channel')
    to = (data.get('to') or '').strip()
    user = current_user()

    if channel == 'sms':
        if not sms.twilio_configured():
            return jsonify({'error': 'SMS is not configured'}), 503
        to = to or user.get('phone_number')
        if not to:
            return jsonify({'error': 'No destination number'}), 400
        sms.send_sms(user, to, note['content'])
        return jsonify({'success': True})

    if channel == 'email':
        if not email_inbound.mailgun_send_configured():
            return jsonify({'error': 'Email sending is not configured'}), 503
        to = to or user.get('email')
        if not to:
            return jsonify({'error': 'No destination address'}), 400
        first_line = (note['content'] or '').strip().split('\n')[0][:80] or 'Note'
        if email_inbound.send_email(to, f'Remndrs: {first_line}', note['content']):
            return jsonify({'success': True})
        return jsonify({'error': 'Email send failed'}), 502

    return jsonify({'error': 'channel must be sms or email'}), 400


# ── Tags ─────────────────────────────────────────────────

@app.route('/api/tags')
def api_list_tags():
    return jsonify(db.list_tags())


@app.route('/api/tags', methods=['POST'])
def api_create_tag():
    data = request.get_json(silent=True) or {}
    tag = db.create_tag(data.get('name', ''), data.get('color'),
                        created_by=session['user_id'])
    if not tag:
        return jsonify({'error': 'Invalid tag name'}), 400
    return jsonify(tag), 201


@app.route('/api/tags/<int:tag_id>', methods=['PATCH'])
def api_update_tag(tag_id):
    data = request.get_json(silent=True) or {}
    tag = db.update_tag(tag_id, name=data.get('name'), color=data.get('color'))
    if not tag:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(tag)


@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def api_delete_tag(tag_id):
    db.delete_tag(tag_id)
    return jsonify({'success': True})


# ── Reminders ────────────────────────────────────────────

@app.route('/api/reminders')
def api_list_reminders():
    return jsonify(db.list_reminders(session['user_id']))


@app.route('/api/reminders/pending')
def api_pending_reminders():
    return jsonify(db.pending_reminders(session['user_id']))


@app.route('/api/reminders', methods=['POST'])
def api_create_reminder():
    data = request.get_json(silent=True) or {}
    if not data.get('message') or not data.get('fire_at'):
        return jsonify({'error': 'message and fire_at are required'}), 400
    reminder = db.create_reminder(
        session['user_id'], data['message'], data['fire_at'],
        notify_sms=data.get('notify_sms', True),
        notify_web=data.get('notify_web', True),
        note_id=data.get('note_id'))
    return jsonify(reminder), 201


@app.route('/api/reminders/<rem_id>', methods=['DELETE'])
def api_delete_reminder(rem_id):
    reminder = db.get_reminder(rem_id)
    if not reminder or reminder['user_id'] != session['user_id']:
        return jsonify({'error': 'Not found'}), 404
    db.delete_reminder(rem_id)
    return jsonify({'success': True})


# ── Link preview ─────────────────────────────────────────

def _youtube_id(url):
    m = re.search(
        r'(?:youtu\.be/|youtube\.com/(?:watch\?(?:[^&]*&)*v=|embed/|shorts/|live/))'
        r'([\w-]{11})', url)
    return m.group(1) if m else None


def _meta(html, *names):
    for name in names:
        m = re.search(
            r'<meta[^>]+(?:property|name)=["\']' + re.escape(name) +
            r'["\'][^>]*content=["\']([^"\']*)["\']', html, re.IGNORECASE)
        if not m:
            m = re.search(
                r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']' +
                re.escape(name) + r'["\']', html, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


# Titles served by CDN/bot walls (Akamai, Cloudflare, …) instead of the real
# page. Scraping one of these used to surface "Access Denied" as the preview;
# we now refuse them and self-heal any that were cached before this fix.
_BLOCK_TITLES = {
    'access denied', 'forbidden', '403 forbidden', '401 unauthorized',
    'access to this page has been denied', 'pardon our interruption',
    'attention required! | cloudflare', 'just a moment...', 'are you a robot?',
}


def _looks_blocked(title):
    return bool(title) and title.strip().lower() in _BLOCK_TITLES


@app.route('/api/preview')
def api_link_preview():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL'}), 400
    cached = db.get_link_preview(url)
    if cached:
        if _looks_blocked(cached.get('title')):
            db.delete_link_preview(url)  # drop a previously-cached block page
        else:
            return jsonify(cached)

    # YouTube serves its og: tags behind bot/consent walls that the plain
    # scraper below trips over, so a link to a video showed no card at all.
    # oEmbed gives a reliable title; the thumbnail URL is derivable from the
    # video id, so a YouTube link always renders a preview now.
    yt = _youtube_id(url)
    if yt:
        title, image = None, f'https://img.youtube.com/vi/{yt}/hqdefault.jpg'
        try:
            r = http.get('https://www.youtube.com/oembed',
                         params={'url': f'https://www.youtube.com/watch?v={yt}',
                                 'format': 'json'}, timeout=5)
            if r.ok:
                j = r.json()
                title = j.get('title') or title
                image = j.get('thumbnail_url') or image
        except Exception:
            pass
        preview = {
            'url': url, 'title': title or 'YouTube video', 'description': None,
            'image': image, 'favicon': None, 'site_name': 'YouTube',
        }
        # Only cache once we have the real title — otherwise a transient oEmbed
        # failure would freeze the generic "YouTube video" label forever.
        if title:
            db.save_link_preview(url, preview['title'], preview['description'],
                                 preview['image'], preview['favicon'],
                                 preview['site_name'])
        return jsonify(preview)

    try:
        resp = http.get(url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; Remndrs/1.0)'})
        # A 403/blocked page still has a body (e.g. an Akamai "Access Denied"
        # page); scraping it cached a junk title. Reject non-OK responses.
        resp.raise_for_status()
        html = resp.text[:500000]
        title = _meta(html, 'og:title')
        if not title:
            m = re.search(r'<title[^>]*>(.*?)</title>', html,
                          re.IGNORECASE | re.DOTALL)
            title = m.group(1).strip() if m else None
        # No usable title, or a CDN block wall that returned 200 — render no card
        # rather than a misleading one, and don't poison the cache with it.
        if not title or _looks_blocked(title):
            return jsonify({'error': 'Could not fetch preview'}), 200
        preview = {
            'url': url,
            'title': title,
            'description': _meta(html, 'og:description', 'description'),
            'image': _meta(html, 'og:image'),
            'favicon': None,
            'site_name': _meta(html, 'og:site_name'),
        }
        db.save_link_preview(url, preview['title'], preview['description'],
                             preview['image'], preview['favicon'],
                             preview['site_name'])
        return jsonify(preview)
    except Exception:
        # A failed preview is not an app error
        return jsonify({'error': 'Could not fetch preview'}), 200


# ── Attachments ──────────────────────────────────────────

@app.route('/api/attachments/<path:filename>', methods=['GET'])
def api_get_attachment(filename):
    record = db.get_attachment_by_filename(os.path.basename(filename))
    user = current_user()
    if not record:
        return jsonify({'error': 'Not found'}), 404
    if record['user_id'] != user['id'] and record['feed'] != 'shared':
        return jsonify({'error': 'Not found'}), 404
    owner = db.get_user(record['user_id'])
    path = attachments_module.resolve_path(record['saved_filename'], owner['name'])
    if not path:
        return jsonify({'error': 'Not found'}), 404
    return send_file(path, mimetype=record.get('mime_type') or None)


@app.route('/api/attachments', methods=['POST'])
def api_upload_attachment():
    note_id = request.form.get('note_id')
    note = db.get_note(note_id) if note_id else None
    if not _can_see(note, session['user_id']):
        return jsonify({'error': 'Note not found'}), 404
    upload = request.files.get('file')
    if not upload or not upload.filename:
        return jsonify({'error': 'No file'}), 400
    try:
        saved = attachments_module.save(upload.read(), upload.filename,
                                        note_id, current_user(),
                                        mime_type=upload.mimetype)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'saved_filename': saved,
                    'markdown': attachments_module.markdown_link(saved)}), 201


# ── Voice ────────────────────────────────────────────────

@app.route('/api/voice/transcribe', methods=['POST'])
def api_voice_transcribe():
    if not voice.openai_configured():
        return jsonify({'error': 'Voice transcription is not configured'}), 503
    upload = request.files.get('audio')
    if not upload:
        return jsonify({'error': 'No audio file'}), 400
    suffix = os.path.splitext(upload.filename or 'audio.webm')[1] or '.webm'
    tmp_path = os.path.join(UPLOADS_DIR, f'{uuid.uuid4().hex}{suffix}')
    try:
        upload.save(tmp_path)
        raw = voice.transcribe(tmp_path)
        transcript = voice.clean_transcript(raw)
        tags = voice.extract_voice_tags(transcript)
        return jsonify({'transcript': transcript, 'tags': tags,
                        'suggested_tags': tags})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        log.exception('Transcription failed')
        return jsonify({'error': 'Transcription failed'}), 500
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ── Calendar ─────────────────────────────────────────────

@app.route('/api/calendar/events')
def api_calendar_events():
    start = request.args.get('from') or (
        datetime.now() - timedelta(days=7)).isoformat(timespec='seconds')
    end = request.args.get('to') or (
        datetime.now() + timedelta(days=30)).isoformat(timespec='seconds')
    events = db.list_calendar_events(session['user_id'], start, end)
    return jsonify(events)


@app.route('/api/calendar/events/<event_id>')
def api_calendar_event(event_id):
    event = db.get_calendar_event(event_id)
    if not event or (event['user_id'] != session['user_id']
                     and event['feed'] != 'shared'):
        return jsonify({'error': 'Not found'}), 404
    event['notes'] = db.list_calendar_notes(event_id)
    return jsonify(event)


@app.route('/api/calendar/calendars')
def api_calendar_list():
    import calendar_sync
    return jsonify(calendar_sync.discover_calendars(session['user_id']))


@app.route('/api/calendar/notes', methods=['POST'])
def api_create_calendar_note():
    data = request.get_json(silent=True) or {}
    event = db.get_calendar_event(data.get('event_id', ''))
    if not event:
        return jsonify({'error': 'Event not found'}), 404
    note = db.create_calendar_note(event['id'], session['user_id'],
                                   data.get('content', ''), tags=data.get('tags'))
    owner = db.get_user(event['user_id'])
    files.write_event_stub(event, owner['name'],
                           existing_filename=_event_stub_name(event, owner),
                           extra_content=note['content'])
    return jsonify(note), 201


def _event_stub_name(event, owner):
    import calendar_sync
    return calendar_sync._stub_filename(event, owner)


@app.route('/api/calendar/notes/<cal_note_id>', methods=['PATCH'])
def api_update_calendar_note(cal_note_id):
    existing = db.get_calendar_note(cal_note_id)
    if not existing or existing['user_id'] != session['user_id']:
        return jsonify({'error': 'Not found'}), 404
    data = request.get_json(silent=True) or {}
    note = db.update_calendar_note(cal_note_id, content=data.get('content'),
                                   tags=data.get('tags'))
    return jsonify(note)


@app.route('/api/calendar/notes/<cal_note_id>', methods=['DELETE'])
def api_delete_calendar_note(cal_note_id):
    existing = db.get_calendar_note(cal_note_id)
    if not existing or existing['user_id'] != session['user_id']:
        return jsonify({'error': 'Not found'}), 404
    db.delete_calendar_note(cal_note_id)
    return jsonify({'success': True})


@app.route('/api/calendar/prefs')
def api_calendar_prefs():
    return jsonify(db.get_calendar_prefs(session['user_id']))


@app.route('/api/calendar/prefs', methods=['PATCH'])
def api_update_calendar_pref():
    data = request.get_json(silent=True) or {}
    if not data.get('calendar_name'):
        return jsonify({'error': 'calendar_name required'}), 400
    db.upsert_calendar_pref(session['user_id'], data['calendar_name'],
                            enabled=data.get('enabled'), feed=data.get('feed'))
    return jsonify({'success': True})


@app.route('/api/calendar/sync', methods=['POST'])
def api_calendar_sync():
    import calendar_sync
    try:
        calendar_sync.sync_user_calendars(session['user_id'])
        return jsonify({'success': True, 'synced_at': db.now_iso()})
    except Exception as e:
        log.exception('Manual calendar sync failed')
        return jsonify({'error': str(e)}), 500


@app.route('/api/notes/<note_id>/to-event', methods=['POST'])
def api_note_to_event(note_id):
    note = db.get_note(note_id)
    if not _can_see(note, session['user_id']):
        return jsonify({'error': 'Not found'}), 404
    data = request.get_json(silent=True) or {}
    required = ('calendar_name', 'start_at', 'end_at')
    if not all(data.get(k) for k in required):
        return jsonify({'error': 'calendar_name, start_at, end_at required'}), 400
    import calendar_sync
    try:
        uid = calendar_sync.create_event_from_note(
            note, session['user_id'], data['calendar_name'],
            data['start_at'], data['end_at'], bool(data.get('all_day')))
        return jsonify({'success': True, 'uid': uid}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        log.exception('Could not create calendar event')
        return jsonify({'error': 'Could not create calendar event'}), 500


# ── SSE ──────────────────────────────────────────────────

@app.route('/api/stream')
def stream():
    user_id = session.get('user_id')
    if not user_id:
        return '', 401

    def event_generator():
        import queue as _queue
        q = sse.subscribe(user_id)
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield f'data: {json.dumps(event)}\n\n'
                except _queue.Empty:
                    yield 'data: {"type": "heartbeat"}\n\n'
        finally:
            sse.unsubscribe(user_id, q)

    return Response(event_generator(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


# ── MCP (Claude connector) ───────────────────────────────

@app.route('/mcp', methods=['POST', 'GET', 'DELETE'])
@app.route('/mcp/<token>', methods=['POST', 'GET', 'DELETE'])
def mcp_endpoint(token=None):
    """Remote MCP server for Claude. Two auth forms resolve to the same
    api_tokens row: the capability URL /mcp/<token> (claude.ai custom
    connectors can't send headers) and Authorization: Bearer at bare /mcp
    (Claude Code). The token is a secret — it appears in access logs, so
    rotating it is one click in Settings → Integrations → Claude."""
    if request.method != 'POST':
        # Stateless server: no GET notification stream, no DELETE session
        # termination — 405 is what the MCP spec prescribes for both.
        return Response(status=405, headers={'Allow': 'POST'})
    user = (db.get_user_by_token_hash(_hash_token(token)) if token
            else _user_from_bearer())
    if not user:
        # Capability URL gets a 404 (don't confirm the namespace exists);
        # the bearer form gets a plain 401 for Claude Code's error surface.
        return ('', 404) if token else (jsonify({'error': 'Unauthorized'}), 401)
    body, status = mcp_server.handle(user, request.get_json(silent=True, force=True))
    if body is None:
        return '', status
    return jsonify(body), status


# ── Webhooks ─────────────────────────────────────────────

@app.route('/webhooks/sms', methods=['POST'])
def webhook_sms():
    if not sms.twilio_configured():
        log.warning('SMS webhook hit but Twilio is not configured')
        return '', 200
    if not sms.validate_twilio_signature(request):
        return '', 403
    reply = sms.handle_inbound(request.form)
    twiml = '<?xml version="1.0" encoding="UTF-8"?><Response>'
    if reply:
        from xml.sax.saxutils import escape
        twiml += f'<Message>{escape(reply)}</Message>'
    twiml += '</Response>'
    return Response(twiml, mimetype='text/xml')


@app.route('/webhooks/telegram', methods=['POST'])
def webhook_telegram():
    if not telegram.telegram_configured():
        return '', 200
    if not telegram.verify_secret(request):
        return '', 403
    telegram.handle_update(request.get_json(silent=True) or {})
    return '', 200


@app.route('/webhooks/voice/answer', methods=['POST'])
def webhook_voice_answer():
    if not sms.twilio_configured() or not sms.validate_twilio_signature(request):
        return '', 403
    twiml = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<Response><Say>Recording. Hang up when done.</Say>'
             '<Record maxLength="300" playBeep="true" '
             'recordingStatusCallback="/webhooks/voice"/></Response>')
    return Response(twiml, mimetype='text/xml')


@app.route('/webhooks/voice', methods=['POST'])
def webhook_voice():
    if not sms.twilio_configured() or not sms.validate_twilio_signature(request):
        return '', 403
    recording_url = request.form.get('RecordingUrl')
    to_number = request.form.get('To') or request.form.get('Called', '')
    caller = request.form.get('From') or request.form.get('Caller', '')
    user = db.get_user_by_twilio_number(to_number)
    if not recording_url or not user:
        return '', 200
    if not voice.openai_configured():
        log.warning('Voice recording received but OPENAI_API_KEY is not set')
        return '', 200

    tmp_path = os.path.join(UPLOADS_DIR, f'{uuid.uuid4().hex}.mp3')
    try:
        auth = (os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
        resp = http.get(f'{recording_url}.mp3', auth=auth, timeout=60)
        resp.raise_for_status()
        with open(tmp_path, 'wb') as f:
            f.write(resp.content)
        transcript = voice.clean_transcript(voice.transcribe(tmp_path))
        tags = voice.extract_voice_tags(transcript)
        feed = 'shared' if 'SHARED' in tags else 'private'
        note = db.create_note(user['id'], content=transcript, source='voice',
                              feed=feed, tags=tags)
        filename = files.write_note_file(note, user['name'])
        note = db.update_note(note['id'], filename=filename)
        sse.push_note_event('note_created', note)
        if caller:
            sms.send_sms(user, caller,
                         f'✓ Voice note saved: "{transcript[:80]}"')
    except Exception:
        log.exception('Voice webhook processing failed')
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return '', 200


@app.route('/webhooks/email', methods=['POST'])
def webhook_email():
    if not email_inbound.mailgun_configured():
        log.warning('Email webhook hit but Mailgun is not configured')
        return '', 200
    sig = request.form
    if not email_inbound.verify_mailgun_signature(
            sig.get('token', ''), sig.get('timestamp', ''), sig.get('signature', '')):
        return '', 403
    file_items = [request.files[k] for k in request.files]
    email_inbound.process_inbound(request.form, file_items)
    return '', 200


# ── Startup ──────────────────────────────────────────────

def pick_port():
    # An explicit PORT is honored exactly — never drift. Behind the Cloudflare
    # tunnel (which forwards one fixed port) a silent fallback would point the
    # tunnel at a dead port and serve 502s.
    if os.getenv('PORT'):
        return int(os.getenv('PORT'))
    # Otherwise scan, but match the server's own SO_REUSEADDR so a port still in
    # TIME_WAIT from a just-restarted instance doesn't fool the probe into
    # drifting to 3001 (the exact cause of the 3000→3001 service-restart bug).
    for port in (3000, 3001, 3002):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return 3000


if __name__ == '__main__':
    reminders.start()
    port = pick_port()
    log.info('Remndrs running on http://localhost:%d', port)
    app.run(host='0.0.0.0', port=port, threaded=True)
