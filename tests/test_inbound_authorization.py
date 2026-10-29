"""Provider-valid requests still need an authorized human sender (synthetic only)."""
import pytest
from twilio.request_validator import RequestValidator

import database as db
import sms

TO = '+15551234567'
OWNER = '+15557654321'
OTHER = '+15550000099'
KEY = 'synthetic-provider-key'
CALL = 'CA' + '1' * 32


@pytest.fixture(autouse=True)
def provider(monkeypatch):
    monkeypatch.setenv('TWILIO_ACCOUNT_SID', 'synthetic-account')
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', KEY)


def signed_post(client, path, form):
    signature = RequestValidator(KEY).compute_signature('http://localhost' + path, form)
    return client.post(path, data=form, headers={'X-Twilio-Signature': signature})


@pytest.mark.parametrize('body', ['LIST', 'GET #PRIVATE', 'FIND synthetic',
                                  'unwanted note', 'REMIND ME tomorrow call'])
def test_valid_provider_signature_does_not_authorize_stranger(client, make_user, make_note, body):
    user = make_user('Owner', phone_number=OWNER, twilio_number=TO)
    make_note(user, content='synthetic private content', tags=['PRIVATE'])
    before = db.list_notes(user['id'])
    response = signed_post(client, '/webhooks/sms', {'To': TO, 'From': OTHER, 'Body': body})
    assert response.status_code == 403
    assert 'synthetic private content' not in response.get_data(as_text=True)
    assert db.list_notes(user['id']) == before
    assert db.list_reminders(user['id']) == []


@pytest.mark.parametrize('sender', ['', 'anonymous', '5557654321', '+15557654321ext9',
                                    '++15557654321', '+000000000', '+15557654321;bad'])
def test_missing_malformed_sender_denied(client, make_user, sender):
    make_user('Owner', phone_number=OWNER, twilio_number=TO)
    form = {'To': TO, 'Body': 'LIST'}
    if sender:
        form['From'] = sender
    assert signed_post(client, '/webhooks/sms', form).status_code == 403


@pytest.mark.parametrize('personal', [None, '', '5557654321'])
def test_no_valid_personal_number_fails_closed(client, make_user, personal):
    make_user('Owner', phone_number=personal, twilio_number=TO)
    assert signed_post(client, '/webhooks/sms', {'To': TO, 'From': OWNER, 'Body': 'LIST'}).status_code == 403


def test_destination_owner_must_match_sender(client, make_user, make_note):
    first = make_user('First', phone_number=OWNER, twilio_number=TO)
    second = make_user('Second', phone_number=OTHER, twilio_number='+15550000088')
    make_note(second, content='second private')
    assert signed_post(client, '/webhooks/sms', {'To': second['twilio_number'], 'From': OWNER, 'Body': 'LIST'}).status_code == 403
    assert signed_post(client, '/webhooks/sms', {'To': '+15550000077', 'From': OWNER, 'Body': 'LIST'}).status_code == 403


def test_duplicate_destination_mapping_denied(client, make_user):
    make_user('First', phone_number=OWNER, twilio_number=TO)
    make_user('Second', phone_number=OWNER, twilio_number='+1 (555) 123-4567')
    assert signed_post(client, '/webhooks/sms', {'To': TO, 'From': OWNER, 'Body': 'LIST'}).status_code == 403


def test_display_format_normalized_and_owner_commands_work(client, make_user, make_note):
    user = make_user('Owner', phone_number='+1 (555) 765-4321', twilio_number='+1 555.123.4567')
    make_note(user, content='synthetic private owner note')
    reply = signed_post(client, '/webhooks/sms', {'To': TO, 'From': OWNER, 'Body': 'LIST'})
    assert reply.status_code == 200
    assert 'synthetic private owner note' in reply.get_data(as_text=True)
    created = signed_post(client, '/webhooks/sms', {'To': TO, 'From': OWNER, 'Body': 'new owner note', 'NumMedia': '0'})
    assert created.status_code == 200
    assert any(n['content'] == 'new owner note' for n in db.list_notes(user['id']))


def test_signature_still_required(client, make_user, monkeypatch):
    make_user('Owner', phone_number=OWNER, twilio_number=TO)
    monkeypatch.setattr(sms, 'authorized_inbound_user', lambda *a: pytest.fail('must check signature first'))
    response = client.post('/webhooks/sms', data={'To': TO, 'From': OWNER, 'Body': 'LIST'},
                           headers={'X-Twilio-Signature': 'invalid'})
    assert response.status_code == 403


@pytest.mark.parametrize('path', ['/webhooks/voice/answer', '/webhooks/voice'])
@pytest.mark.parametrize('sender', [OTHER, '', 'anonymous'])
def test_voice_denied_before_recording_or_provider_work(client, make_user, monkeypatch, path, sender):
    import app
    user = make_user('Owner', phone_number=OWNER, twilio_number=TO)
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-key')
    monkeypatch.setattr(app.http, 'get', lambda *a, **k: pytest.fail('must not download audio'))
    monkeypatch.setattr(app.voice, 'transcribe', lambda *a: pytest.fail('must not transcribe'))
    monkeypatch.setattr(sms, 'send_sms', lambda *a: pytest.fail('must not send SMS'))
    response = signed_post(client, path, {'To': TO, 'From': sender, 'CallSid': CALL, 'RecordingStatus': 'completed', 'RecordingUrl': 'https://example.invalid/audio'})
    assert response.status_code == 403
    assert '<Record' not in response.get_data(as_text=True)
    assert db.list_notes(user['id']) == []


def test_authorized_voice_answer_preserved(client, make_user):
    make_user('Owner', phone_number=OWNER, twilio_number=TO)
    response = signed_post(client, '/webhooks/voice/answer', {'To': TO, 'From': OWNER, 'CallSid': CALL})
    assert response.status_code == 200
    assert '<Record' in response.get_data(as_text=True)


def test_authorized_voice_callback_preserved_with_mock_providers(client, make_user, monkeypatch):
    import app
    user = make_user('Owner', phone_number=OWNER, twilio_number=TO)
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-key')
    class Audio:
        content = b'synthetic audio'
        def raise_for_status(self): pass
    monkeypatch.setattr(app.http, 'get', lambda *a, **k: Audio())
    monkeypatch.setattr(app.voice, 'transcribe', lambda *a: 'synthetic voice note')
    monkeypatch.setattr(app.voice, 'smart_clean', lambda s: s)
    monkeypatch.setattr(sms, 'send_sms', lambda *a: None)
    import xml.etree.ElementTree as ET
    answer = signed_post(client, '/webhooks/voice/answer', {'To': TO, 'From': OWNER, 'CallSid': CALL})
    callback = ET.fromstring(answer.data).find('Record').attrib['recordingStatusCallback']
    form = {'CallSid': CALL, 'RecordingStatus': 'completed', 'RecordingUrl': 'https://example.invalid/audio'}
    # Documented status-callback payload: no From or To.
    response = signed_post(client, callback, form)
    assert response.status_code == 200
    assert db.list_notes(user['id'])[0]['content'] == 'synthetic voice note'
    assert signed_post(client, callback, form).status_code == 200
    assert len(db.list_notes(user['id'])) == 1


def test_direct_sms_dispatch_also_rejects_untrusted_sender(make_user, make_note):
    user = make_user('Owner', phone_number=OWNER, twilio_number=TO)
    make_note(user, content='synthetic private note')
    assert sms.handle_inbound({'To': TO, 'From': OTHER, 'Body': 'LIST'}) is None


@pytest.mark.parametrize('path', ['/webhooks/voice/answer', '/webhooks/voice'])
def test_voice_invalid_signature_rejected_before_authorization(client, make_user, monkeypatch, path):
    make_user('Owner', phone_number=OWNER, twilio_number=TO)
    monkeypatch.setattr(sms, 'authorized_inbound_user', lambda *a: pytest.fail('signature first'))
    assert client.post(path, data={'To': TO, 'From': OWNER},
                       headers={'X-Twilio-Signature': 'invalid'}).status_code == 403


@pytest.mark.parametrize('case', ['tampered', 'expired', 'mismatched-call', 'changed-profile', 'lost-context'])
def test_recording_context_fails_closed(client, make_user, monkeypatch, case):
    import app
    import itsdangerous.timed
    import time
    user = make_user('Owner', phone_number=OWNER, twilio_number=TO)
    if case == 'expired':
        with monkeypatch.context() as past:
            past.setattr(itsdangerous.timed.TimestampSigner, 'get_timestamp', lambda self: int(time.time()) - 1000)
            token = app._new_voice_context(user, CALL)
    else:
        token = app._new_voice_context(user, CALL)
    if case == 'tampered':
        token += 'invalid'
    if case == 'changed-profile':
        db.update_user_contact(user['id'], phone_number=OTHER)
    if case == 'lost-context':
        app._VOICE_CONTEXTS.clear()  # process restart deliberately fails closed
    form = {'CallSid': 'CA' + '2' * 32 if case == 'mismatched-call' else CALL,
            'RecordingStatus': 'completed', 'RecordingUrl': 'https://example.invalid/audio'}
    monkeypatch.setattr(app.http, 'get', lambda *a, **k: pytest.fail('no download'))
    response = signed_post(client, '/webhooks/voice?context=' + token, form)
    assert response.status_code == 403
    assert db.list_notes(user['id']) == []


def test_voice_context_retries_pre_note_failure_without_duplicates(client, make_user, monkeypatch):
    import app
    user = make_user('Owner', phone_number=OWNER, twilio_number=TO)
    token = app._new_voice_context(user, CALL)
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-key')
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic download failure')
    monkeypatch.setattr(app.http, 'get', fail)
    form = {'CallSid': CALL, 'RecordingStatus': 'completed', 'RecordingUrl': 'https://example.invalid/audio'}
    assert signed_post(client, '/webhooks/voice?context=' + token, form).status_code == 500
    assert db.list_notes(user['id']) == []
    assert all(r['state'] != 'processing' for r in app._VOICE_CONTEXTS.values())


def test_inflight_recording_callback_not_processed_twice(client, make_user, monkeypatch):
    import app
    user = make_user('Owner', phone_number=OWNER, twilio_number=TO)
    token = app._new_voice_context(user, CALL)
    assert app._claim_voice_context(token, CALL)[2] == 'pending'
    monkeypatch.setattr(app.http, 'get', lambda *a, **k: pytest.fail('no second download'))
    form = {'CallSid': CALL, 'RecordingStatus': 'completed', 'RecordingUrl': 'https://example.invalid/audio'}
    assert signed_post(client, '/webhooks/voice?context=' + token, form).status_code == 409


def test_answer_retry_reuses_one_call_context(make_user):
    import app
    user = make_user('Owner', phone_number=OWNER, twilio_number=TO)
    first = app._new_voice_context(user, CALL)
    assert app._new_voice_context(user, CALL) == first


@pytest.mark.parametrize('payload', [[], None, {'call': CALL},
    {'call': CALL, 'user': [], 'config': 'x', 'nonce': 'x'},
    {'call': CALL, 'user': 'x', 'config': 'x', 'nonce': []}])
def test_malformed_signed_context_denied_not_server_error(client, payload):
    import app
    token = app._voice_serializer().dumps(payload)
    form = {'CallSid': CALL, 'RecordingStatus': 'completed', 'RecordingUrl': 'https://example.invalid/audio'}
    assert signed_post(client, '/webhooks/voice?context=' + token, form).status_code == 403
