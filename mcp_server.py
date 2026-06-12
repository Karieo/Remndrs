"""Remote MCP server so Claude can capture and search notes.

Streamable HTTP transport, stateless: one POST endpoint speaking JSON-RPC 2.0
(initialize / ping / tools/list / tools/call). app.py owns the route and
resolves the user from a capability-URL token or an Authorization bearer —
both backed by the existing api_tokens table — before calling handle().

Add it to claude.ai as a custom connector (Settings → Connectors → Add custom
connector) using the URL minted in ⚙ Settings → Integrations → Claude, or to
Claude Code with:
  claude mcp add --transport http remndrs https://YOUR-URL/mcp \
      --header "Authorization: Bearer TOKEN"
"""

import logging
from datetime import datetime

import database as db
import files
import sms  # reuse the channel helpers (extract_hashtags/_snippet/_fmt_date)
import sse

log = logging.getLogger(__name__)

PROTOCOL_VERSIONS = ('2025-06-18', '2025-03-26', '2024-11-05')
LATEST_PROTOCOL = '2025-06-18'
SERVER_VERSION = '0'  # app.py injects its VERSION after import
INSTRUCTIONS = (
    "Remndrs is the user's personal notes and reminders app. Use add_note to "
    "save notes (#hashtags in the content become tags), add_reminder for "
    "time-based reminders, and search_notes / recent_notes / get_notes_by_tag "
    "to read what the user has saved. Times are in the user's local timezone.")

MAX_RESULTS = 20


class ToolError(Exception):
    """A tool-domain failure Claude can read and correct (bad time string,
    missing argument) — returned as result.isError, not a JSON-RPC error."""


# ── Tool implementations ─────────────────────────────────

def _tool_add_note(user, args):
    content = (args.get('content') or '').strip()
    if not content:
        raise ToolError('content is required and cannot be empty.')
    tags = ['CLAUDE'] + sms.extract_hashtags(content) + \
        [str(t) for t in (args.get('tags') or [])]
    tags = list(dict.fromkeys(t.upper() for t in tags if t))
    feed = 'shared' if (args.get('shared') or 'SHARED' in tags) else 'private'
    todo_items = [str(t) for t in (args.get('todo_items') or []) if str(t).strip()]
    todos = [{'text': t, 'checked': False} for t in todo_items]

    note = db.create_note(user['id'], content=content,
                          note_type='todo' if todos else 'note',
                          feed=feed, source='claude', tags=tags, todos=todos)
    filename = files.write_note_file(note, user['name'])
    note = db.update_note(note['id'], filename=filename)
    sse.push_note_event('note_created', note)

    title = content.split('\n')[0][:60]
    extras = f' with {len(todos)} checklist items' if todos else ''
    return (f'Saved note "{title}"{extras} to the {feed} feed '
            f"(tags: {', '.join(tags)}).")


def _tool_add_reminder(user, args):
    when = (args.get('when') or '').strip()
    message = (args.get('message') or '').strip()
    if not when or not message:
        raise ToolError('Both "when" and "message" are required.')

    fire_at = None
    try:
        fire_at = datetime.fromisoformat(when)
    except ValueError:
        try:
            import dateparser
            fire_at = dateparser.parse(
                when, settings={'PREFER_DATES_FROM': 'future'})
        except ImportError:
            pass
    if not fire_at:
        raise ToolError(f'Could not understand the time "{when}". Try an ISO '
                        'timestamp like 2026-06-13T09:00 or natural language '
                        'like "tomorrow at 9am".')
    if fire_at <= datetime.now():
        raise ToolError(f'"{when}" reads as a past time '
                        f'({fire_at.isoformat(timespec="minutes")}) — '
                        'reminders must be in the future.')

    db.create_reminder(user['id'], message,
                       fire_at.isoformat(timespec='seconds'),
                       notify_sms=True, notify_web=True)
    human = fire_at.strftime('%A, %B %-d at %-I:%M %p')
    return f'Reminder set for {human}: "{message}"'


def _format_notes(notes):
    lines = []
    for n in notes:
        tags = ' '.join('#' + t['name'] for t in n['tags'])
        lines.append(f"• {sms._fmt_date(n['created_at'])} · {sms._snippet(n, 200)}"
                     + (f'  [{tags}]' if tags else ''))
    return '\n'.join(lines)


def _limit(args):
    try:
        return max(1, min(int(args.get('limit', 5)), MAX_RESULTS))
    except (TypeError, ValueError):
        return 5


def _tool_search_notes(user, args):
    query = (args.get('query') or '').strip()
    if not query:
        raise ToolError('query is required.')
    notes = db.search_user_notes(user['id'], query, limit=_limit(args))
    if not notes:
        return f'No notes found for "{query}".'
    return f'{len(notes)} note(s) matching "{query}":\n' + _format_notes(notes)


def _tool_recent_notes(user, args):
    notes = db.recent_notes(user['id'], limit=_limit(args))
    if not notes:
        return 'No notes yet.'
    return f'{len(notes)} most recent note(s):\n' + _format_notes(notes)


def _tool_get_notes_by_tag(user, args):
    tag = (args.get('tag') or '').strip()
    if not tag:
        raise ToolError('tag is required.')
    notes = db.notes_by_tag(user['id'], tag, limit=_limit(args))
    name = db.normalize_tag(tag)
    if not notes:
        return f'No notes tagged #{name}.'
    return f'{len(notes)} note(s) tagged #{name}:\n' + _format_notes(notes)


TOOLS = [
    {'name': 'add_note',
     'description': ('Save a new note to Remndrs. Use when the user asks to '
                     'save, jot down, or remember something. Hashtags in the '
                     'content (#likethis) automatically become tags. The first '
                     'line becomes the note title.'),
     'inputSchema': {'type': 'object', 'properties': {
         'content': {'type': 'string',
                     'description': 'Note text (Markdown supported).'},
         'tags': {'type': 'array', 'items': {'type': 'string'},
                  'description': 'Optional extra tag names; stored uppercase '
                                 'and deduplicated.'},
         'shared': {'type': 'boolean',
                    'description': "True to post to the household's shared "
                                   "feed instead of the user's private feed. "
                                   'Default false.'},
         'todo_items': {'type': 'array', 'items': {'type': 'string'},
                        'description': 'Optional checklist items; providing '
                                       'any turns the note into a todo list '
                                       '(content becomes its title).'}},
         'required': ['content']}},
    {'name': 'add_reminder',
     'description': ('Set a reminder that notifies the user in the app (and '
                     'by SMS if configured). Use when the user asks to be '
                     "reminded of something at a time. Times are in the "
                     "user's local timezone."),
     'inputSchema': {'type': 'object', 'properties': {
         'when': {'type': 'string',
                  'description': 'When to fire: ISO 8601 local time '
                                 '("2026-06-13T09:00") or natural language '
                                 '("tomorrow at 9am", "Friday 3pm"). Must be '
                                 'in the future.'},
         'message': {'type': 'string',
                     'description': 'What to remind the user about.'}},
         'required': ['when', 'message']}},
    {'name': 'search_notes',
     'description': ("Search the user's notes (content and todo items) by "
                     "keywords, or by a date ('Jun 11', '2026-06-11', '6/11') "
                     'to find notes created that day. Use before answering '
                     'questions about what the user has saved.'),
     'inputSchema': {'type': 'object', 'properties': {
         'query': {'type': 'string',
                   'description': 'Keywords (every word must match) or a date.'},
         'limit': {'type': 'integer',
                   'description': 'Max results, default 5, max 20.'}},
         'required': ['query']}},
    {'name': 'recent_notes',
     'description': "List the user's most recent notes, newest first.",
     'inputSchema': {'type': 'object', 'properties': {
         'limit': {'type': 'integer',
                   'description': 'How many, default 5, max 20.'}},
         'required': []}},
    {'name': 'get_notes_by_tag',
     'description': ("List the user's notes carrying a given tag (case-"
                     "insensitive, with or without #, e.g. 'shopping')."),
     'inputSchema': {'type': 'object', 'properties': {
         'tag': {'type': 'string', 'description': 'Tag name.'},
         'limit': {'type': 'integer',
                   'description': 'Max results, default 5, max 20.'}},
         'required': ['tag']}},
]

TOOL_HANDLERS = {
    'add_note': _tool_add_note,
    'add_reminder': _tool_add_reminder,
    'search_notes': _tool_search_notes,
    'recent_notes': _tool_recent_notes,
    'get_notes_by_tag': _tool_get_notes_by_tag,
}


# ── JSON-RPC dispatch ────────────────────────────────────

def handle(user, payload):
    """Dispatch a decoded JSON body. Returns (body_or_None, http_status):
    None body + 202 for notification-only payloads, per the MCP spec."""
    if payload is None:
        return _err(None, -32700, 'Parse error'), 200
    if isinstance(payload, list):  # JSON-RPC batch (2025-03-26 clients)
        out = [r for r in (_dispatch(user, m) for m in payload) if r is not None]
        return (out, 200) if out else (None, 202)
    resp = _dispatch(user, payload)
    return (resp, 200) if resp is not None else (None, 202)


def _dispatch(user, msg):
    if not isinstance(msg, dict) or msg.get('jsonrpc') != '2.0':
        return _err(None, -32600, 'Invalid Request')
    method, params = msg.get('method'), msg.get('params') or {}
    msg_id = msg.get('id')
    if method is None or 'id' not in msg:
        # A notification (initialized/cancelled) or a client-side response —
        # nothing to answer.
        return None
    try:
        if method == 'initialize':
            requested = params.get('protocolVersion')
            return _ok(msg_id, {
                'protocolVersion': requested if requested in PROTOCOL_VERSIONS
                                   else LATEST_PROTOCOL,
                'capabilities': {'tools': {}},
                'serverInfo': {'name': 'Remndrs', 'version': SERVER_VERSION},
                'instructions': INSTRUCTIONS,
            })
        if method == 'ping':
            return _ok(msg_id, {})
        if method == 'tools/list':
            return _ok(msg_id, {'tools': TOOLS})
        if method == 'tools/call':
            return _tools_call(user, msg_id, params)
        return _err(msg_id, -32601, f'Method not found: {method}')
    except Exception:
        log.exception('MCP %s failed', method)
        return _err(msg_id, -32603, 'Internal error')


def _tools_call(user, msg_id, params):
    handler = TOOL_HANDLERS.get(params.get('name'))
    if not handler:
        return _err(msg_id, -32602, f"Unknown tool: {params.get('name')}")
    try:
        text = handler(user, params.get('arguments') or {})
        return _ok(msg_id, {'content': [{'type': 'text', 'text': text}],
                            'isError': False})
    except ToolError as e:
        return _ok(msg_id, {'content': [{'type': 'text', 'text': str(e)}],
                            'isError': True})


def _ok(msg_id, result):
    return {'jsonrpc': '2.0', 'id': msg_id, 'result': result}


def _err(msg_id, code, message):
    return {'jsonrpc': '2.0', 'id': msg_id,
            'error': {'code': code, 'message': message}}
