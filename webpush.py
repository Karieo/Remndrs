"""Web Push (VAPID) delivery so reminders reach the browser even with no tab
open — the gap SSE can't cover.

Self-disabling like every other integration: with no VAPID keys in the env it
silently no-ops, and `pywebpush` is imported lazily so the app runs without it
installed. Keys are read at call time (env is editable at runtime from Settings).

Generate a keypair once with:
    python -c "from py_vapid import Vapid01 as V; v=V(); v.generate_keys(); \
        import base64; \
        print('PUBLIC', base64.urlsafe_b64encode(v.public_key.public_bytes(...)))"
or simply `vapid --gen` (py-vapid). Set VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY,
and VAPID_SUBJECT (a mailto: or https: contact).
"""

import json
import logging
import os

import database as db

log = logging.getLogger(__name__)


def configured():
    return bool(os.getenv('VAPID_PRIVATE_KEY') and os.getenv('VAPID_PUBLIC_KEY'))


def public_key():
    """The application server key the browser needs to subscribe."""
    return os.getenv('VAPID_PUBLIC_KEY', '')


def _claims():
    return {'sub': os.getenv('VAPID_SUBJECT', 'mailto:owner@remndrs.local')}


def send_to_user(user_id, title, body, url='/'):
    """Push a notification to every browser the user has subscribed. Expired
    subscriptions (404/410) are pruned. Never raises — best-effort delivery."""
    if not configured():
        return
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        log.warning('pywebpush not installed — skipping web push')
        return

    payload = json.dumps({'title': title, 'body': body, 'url': url})
    private_key = os.getenv('VAPID_PRIVATE_KEY')
    for sub in db.list_push_subscriptions(user_id):
        try:
            webpush(subscription_info=json.loads(sub['subscription']),
                    data=payload,
                    vapid_private_key=private_key,
                    vapid_claims=dict(_claims()))  # pywebpush mutates this dict
        except WebPushException as e:
            status = getattr(getattr(e, 'response', None), 'status_code', None)
            if status in (404, 410):
                db.delete_push_subscription(sub['endpoint'])
                log.info('Pruned expired push subscription for user %s', user_id)
            else:
                log.warning('Web push failed (%s): %s', status, e)
        except Exception:
            log.exception('Web push error')
