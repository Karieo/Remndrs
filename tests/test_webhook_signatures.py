"""Tier 1 — webhook signature verification.

Webhook routes bypass session auth and must instead prove the request came
from the provider. The critical rule for all three: an *unconfigured*
integration (no secret set) must REJECT, never silently accept.
"""

import hashlib
import hmac

import email_inbound
import sms
import telegram


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


# ── Mailgun (HMAC-SHA256) ──────────────────────────────────────────────────

def _mailgun_sign(key, token, timestamp):
    return hmac.new(key.encode(), f'{timestamp}{token}'.encode(),
                    hashlib.sha256).hexdigest()


def test_mailgun_valid_signature_accepted(monkeypatch):
    monkeypatch.setenv('MAILGUN_SIGNING_KEY', 'k3y')
    sig = _mailgun_sign('k3y', 'tok', '12345')
    assert email_inbound.verify_mailgun_signature('tok', '12345', sig) is True


def test_mailgun_tampered_signature_rejected(monkeypatch):
    monkeypatch.setenv('MAILGUN_SIGNING_KEY', 'k3y')
    good = _mailgun_sign('k3y', 'tok', '12345')
    assert email_inbound.verify_mailgun_signature('tok', '12345', good + 'x') is False
    # Wrong token/timestamp also fail.
    assert email_inbound.verify_mailgun_signature('other', '12345', good) is False
    assert email_inbound.verify_mailgun_signature('tok', '99999', good) is False


def test_mailgun_missing_key_rejects(monkeypatch):
    monkeypatch.delenv('MAILGUN_SIGNING_KEY', raising=False)
    assert email_inbound.verify_mailgun_signature('tok', '12345', 'anything') is False


def test_mailgun_none_signature_rejected(monkeypatch):
    monkeypatch.setenv('MAILGUN_SIGNING_KEY', 'k3y')
    assert email_inbound.verify_mailgun_signature('tok', '12345', None) is False


# ── Telegram (shared secret header) ────────────────────────────────────────

def test_telegram_valid_secret_accepted(monkeypatch):
    monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET', 's3cr3t')
    req = _FakeRequest({'X-Telegram-Bot-Api-Secret-Token': 's3cr3t'})
    assert telegram.verify_secret(req) is True


def test_telegram_wrong_secret_rejected(monkeypatch):
    monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET', 's3cr3t')
    req = _FakeRequest({'X-Telegram-Bot-Api-Secret-Token': 'wrong'})
    assert telegram.verify_secret(req) is False


def test_telegram_missing_secret_env_rejects(monkeypatch):
    monkeypatch.delenv('TELEGRAM_WEBHOOK_SECRET', raising=False)
    req = _FakeRequest({'X-Telegram-Bot-Api-Secret-Token': 'anything'})
    assert telegram.verify_secret(req) is False


def test_telegram_missing_header_rejected(monkeypatch):
    monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET', 's3cr3t')
    assert telegram.verify_secret(_FakeRequest({})) is False


# ── Twilio (unconfigured boundary) ─────────────────────────────────────────

def test_twilio_unconfigured_rejects(monkeypatch):
    monkeypatch.delenv('TWILIO_ACCOUNT_SID', raising=False)
    monkeypatch.delenv('TWILIO_AUTH_TOKEN', raising=False)
    # No creds → must reject before even importing the Twilio SDK validator.
    assert sms.validate_twilio_signature(_FakeRequest()) is False
