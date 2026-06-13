"""Tier 2 — natural-language reminder parsing (reminders.parse_remind_text).

dateparser's behaviour can shift across versions, so these tests pin the
contract: future expressions parse to a future ISO timestamp with the reminder
phrase stripped from the message; non-times and past times return None.
"""

from datetime import datetime

import reminders


def test_parse_future_relative_time():
    result = reminders.parse_remind_text('remind me tomorrow at 9am to call mom')
    assert result is not None
    fire_at, message = result
    parsed = datetime.fromisoformat(fire_at)
    assert parsed > datetime.now()
    assert 'call mom' in message.lower()


def test_parse_strips_remind_phrase_from_message():
    result = reminders.parse_remind_text('reminder: tomorrow 3pm dentist appointment')
    assert result is not None
    _fire_at, message = result
    assert 'remind' not in message.lower()
    assert 'dentist' in message.lower()


def test_parse_no_time_returns_none():
    assert reminders.parse_remind_text('just some text with no date in it') is None


def test_parse_past_time_returns_none():
    # A clearly past reference should not become a reminder.
    assert reminders.parse_remind_text('remind me yesterday to do nothing') is None


def test_parse_returns_iso_seconds_precision():
    result = reminders.parse_remind_text('remind me next monday at noon to ship')
    assert result is not None
    fire_at, _ = result
    # isoformat(timespec='seconds') → exactly one ':' in the time portion pair.
    assert datetime.fromisoformat(fire_at)  # round-trips
    assert len(fire_at.split('T')[1].split(':')) == 3
