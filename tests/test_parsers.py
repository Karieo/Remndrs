"""Tier 2 — SMS / Telegram command parsers and hashtag extraction.

These are the channel command grammars (GET / FIND / LIST / REMIND ME / free
text). The routing is pure-ish branching over the message text; note creation
is exercised end-to-end against the temp DB.
"""

import database as db
import sms
import telegram


# ── sms.extract_hashtags (pure) ────────────────────────────────────────────

def test_extract_hashtags_uppercases_and_returns_all():
    assert sms.extract_hashtags('buy #milk and #Eggs') == ['MILK', 'EGGS']


def test_extract_hashtags_allows_digits_and_underscores():
    assert sms.extract_hashtags('#to_do #plan2026') == ['TO_DO', 'PLAN2026']


def test_extract_hashtags_handles_none_and_empty():
    assert sms.extract_hashtags(None) == []
    assert sms.extract_hashtags('no tags here') == []


# ── sms._fmt_date / _snippet (pure) ────────────────────────────────────────

def test_fmt_date_valid_and_invalid():
    assert sms._fmt_date('2026-06-13T09:30:00') == 'Jun 13'
    assert sms._fmt_date(None) == ''
    assert sms._fmt_date('not-a-date') == 'not-a-date'  # first 10 chars fallback


def test_snippet_collapses_whitespace_and_truncates():
    note = {'content': 'a\n\n  b   c', 'type': 'note'}
    assert sms._snippet(note) == 'a b c'
    long = {'content': 'x' * 200, 'type': 'note'}
    assert len(sms._snippet(long, 80)) == 80


def test_snippet_annotates_todo_count():
    note = {'content': 'groceries', 'type': 'todo',
            'todos': [{'text': 'a'}, {'text': 'b'}]}
    assert '(todo, 2 items)' in sms._snippet(note)


# ── sms.handle_inbound routing ─────────────────────────────────────────────

def test_handle_inbound_unknown_number(make_user):
    reply = sms.handle_inbound({'To': '+10000000000', 'Body': 'hi'})
    assert "isn't configured" in reply


def test_handle_inbound_free_text_creates_note(make_user):
    user = make_user('Clay', twilio_number='+15551234567')
    reply = sms.handle_inbound({'To': '+15551234567', 'Body': 'remember the milk',
                               'NumMedia': '0'})
    assert reply == '✓ Saved'
    notes = db.recent_notes(user['id'])
    assert len(notes) == 1
    assert notes[0]['content'] == 'remember the milk'
    assert notes[0]['source'] == 'sms'
    assert 'SMS' in [t['name'] for t in notes[0]['tags']]


def test_handle_inbound_shared_hashtag_routes_to_shared_feed(make_user):
    user = make_user('Clay', twilio_number='+15551234567')
    sms.handle_inbound({'To': '+15551234567', 'Body': 'dinner plan #shared',
                       'NumMedia': '0'})
    note = db.list_notes(user['id'])[0]
    assert note['feed'] == 'shared'


def test_handle_inbound_list_command(make_user, make_note):
    user = make_user('Clay', twilio_number='+15551234567')
    make_note(user, content='note one')
    reply = sms.handle_inbound({'To': '+15551234567', 'Body': 'LIST'})
    assert 'most recent' in reply
    assert 'note one' in reply


def test_handle_inbound_get_command_is_case_insensitive(make_user, make_note):
    user = make_user('Clay', twilio_number='+15551234567')
    make_note(user, content='tagged note', tags=['IDEAS'])
    reply = sms.handle_inbound({'To': '+15551234567', 'Body': 'get #ideas'})
    assert '#IDEAS' in reply
    assert 'tagged note' in reply


def test_handle_inbound_find_command(make_user, make_note):
    user = make_user('Clay', twilio_number='+15551234567')
    make_note(user, content='dentist appointment tuesday')
    reply = sms.handle_inbound({'To': '+15551234567', 'Body': 'FIND dentist'})
    assert 'dentist' in reply


def test_handle_inbound_get_with_no_results(make_user):
    make_user('Clay', twilio_number='+15551234567')
    reply = sms.handle_inbound({'To': '+15551234567', 'Body': 'GET #nope'})
    assert 'No notes tagged #NOPE' in reply


# ── telegram._dispatch / handle_update ─────────────────────────────────────

def test_telegram_help_command(make_user):
    user = make_user('Clay')
    for cmd in ('/start', '/help', 'help', 'HELP'):
        assert 'save' in telegram._dispatch(user, cmd).lower()


def test_telegram_free_text_creates_note(make_user):
    user = make_user('Clay')
    reply = telegram._dispatch(user, 'idea: ship it #work')
    assert reply == '✓ Saved'
    note = db.recent_notes(user['id'])[0]
    assert note['source'] == 'telegram'
    names = [t['name'] for t in note['tags']]
    assert 'TELEGRAM' in names and 'WORK' in names


def test_telegram_handle_update_unlinked_chat_does_not_create_note(make_user, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram, 'send_message', lambda cid, txt: sent.append((cid, txt)))
    telegram.handle_update({'message': {'chat': {'id': 999, 'first_name': 'Sam'},
                                       'text': 'hello'}})
    assert sent and "isn't linked" in sent[0][1]


def test_telegram_handle_update_ignores_empty_message(monkeypatch):
    called = []
    monkeypatch.setattr(telegram, 'send_message', lambda *a: called.append(a))
    telegram.handle_update({'message': {'chat': {'id': 1}, 'text': '   '}})
    telegram.handle_update({})  # no message key at all
    assert called == []
