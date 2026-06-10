"""Remndrs — Flask server: auth, all API routes, webhooks, SSE stream."""

import hashlib
import json
import logging
import os
import re
import secrets
import socket
import tempfile
import uuid
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

import bcrypt
import requests as http
from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, send_file, session)

import attachments as attachments_module
import database as db
import email_inbound
import files
import reminders
import sms
import sse
import voice

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('remndrs')

app = Flask(__name__)

_secret = os.getenv('SESSION_SECRET')
if not _secret:
    _secret = secrets.token_hex(32)
    log.warning('SESSION_SECRET not set — generated a random one '
                '(sessions will not survive restarts)')
app.secret_key = _secret
app.permanent_session_lifetime = timedelta(days=7)

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOADS_DIR, exist_ok=True)


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

PUBLIC_PATHS = ('/login', '/api/auth/login', '/api/auth/token', '/webhooks/', '/static/')


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


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


@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or request.form
    login = (data.get('login') or data.get('email_or_name') or '').strip()
    password = data.get('password') or ''
    user = db.get_user_by_login(login)
    if not user or not bcrypt.checkpw(password.encode(),
                                      user['password_hash'].encode()):
        return jsonify({'error': 'Invalid credentials'}), 401
    session.permanent = True
    session['user_id'] = user['id']
    return jsonify({'success': True,
                    'user': {'id': user['id'], 'name': user['name'],
                             'role': user['role']}})


@app.route('/api/auth/token', methods=['POST'])
def api_create_token():
    """Issue a long-lived bearer token for mobile clients."""
    data = request.get_json(silent=True) or {}
    login = (data.get('login') or '').strip()
    password = data.get('password') or ''
    user = db.get_user_by_login(login)
    if not user or not bcrypt.checkpw(password.encode(),
                                      user['password_hash'].encode()):
        return jsonify({'error': 'Invalid credentials'}), 401
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
    notes = db.list_notes(session['user_id'],
                          tag=request.args.get('tag'),
                          search=request.args.get('search'),
                          source=request.args.get('source'),
                          feed=request.args.get('feed'))
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

    fields = {k: data[k] for k in ('content', 'feed', 'type', 'pinned')
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


@app.route('/api/preview')
def api_link_preview():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL'}), 400
    cached = db.get_link_preview(url)
    if cached:
        return jsonify(cached)
    try:
        resp = http.get(url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; Remndrs/1.0)'})
        html = resp.text[:500000]
        title = _meta(html, 'og:title')
        if not title:
            m = re.search(r'<title[^>]*>(.*?)</title>', html,
                          re.IGNORECASE | re.DOTALL)
            title = m.group(1).strip() if m else None
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
        q = sse.get_queue(user_id)
        while True:
            try:
                event = q.get(timeout=30)
                yield f'data: {json.dumps(event)}\n\n'
            except _queue.Empty:
                yield 'data: {"type": "heartbeat"}\n\n'

    return Response(event_generator(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


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
    preferred = int(os.getenv('PORT', 3000))
    for port in (preferred, 3001, 3002):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return preferred


if __name__ == '__main__':
    reminders.start()
    port = pick_port()
    log.info('Remndrs running on http://localhost:%d', port)
    app.run(host='0.0.0.0', port=port, threaded=True)
