"""Server-Sent Events: per-connection queues so every open tab/device
gets every event. push_note_event() fans shared-feed notes out to all users."""

import queue

_subscribers = {}  # user_id -> list[queue.Queue], one per open stream


def subscribe(user_id):
    q = queue.Queue()
    _subscribers.setdefault(user_id, []).append(q)
    return q


def unsubscribe(user_id, q):
    try:
        _subscribers.get(user_id, []).remove(q)
    except ValueError:
        pass


def push_event(user_id, event_type, data):
    for q in list(_subscribers.get(user_id, [])):
        q.put({'type': event_type, 'data': data})


def push_note_event(event_type, note):
    """Push a note event to its owner, and to all users if it's a shared note."""
    import database as db
    if note.get('feed') == 'shared':
        for user in db.list_users():
            push_event(user['id'], event_type, note)
    else:
        push_event(note['user_id'], event_type, note)
