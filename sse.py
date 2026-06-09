"""Server-Sent Events: per-user event queues pushed to open browser tabs."""

import queue

user_queues = {}  # user_id -> queue.Queue()


def get_queue(user_id):
    if user_id not in user_queues:
        user_queues[user_id] = queue.Queue()
    return user_queues[user_id]


def push_event(user_id, event_type, data):
    q = get_queue(user_id)
    q.put({'type': event_type, 'data': data})


def push_note_event(event_type, note):
    """Push a note event to its owner, and to all users if it's a shared note."""
    import database as db
    if note.get('feed') == 'shared':
        for user in db.list_users():
            push_event(user['id'], event_type, note)
    else:
        push_event(note['user_id'], event_type, note)
