"""Writes and reads .md note files in the iCloud Drive folder.

Every note is a real markdown file with YAML frontmatter, Obsidian-compatible.
If the iCloud folder is unavailable, falls back to ~/Documents/Remndrs.
"""

import logging
import os
import re

log = logging.getLogger(__name__)

_warned_fallback = False


def notes_folder():
    global _warned_fallback
    configured = os.getenv('NOTES_FOLDER',
                           '~/Library/Mobile Documents/com~apple~CloudDocs/Remndrs')
    path = os.path.expanduser(configured)
    parent = os.path.dirname(path)
    if os.path.isdir(parent):
        os.makedirs(path, exist_ok=True)
        return path
    fallback = os.path.expanduser('~/Documents/Remndrs')
    if not _warned_fallback:
        log.warning('iCloud folder unavailable (%s) — falling back to %s', path, fallback)
        _warned_fallback = True
    os.makedirs(fallback, exist_ok=True)
    return fallback


def user_folder(user_name, feed='private'):
    folder = os.path.join(notes_folder(), 'Shared' if feed == 'shared' else user_name)
    os.makedirs(folder, exist_ok=True)
    return folder


def attachments_folder(user_name):
    folder = os.path.join(notes_folder(), user_name, 'attachments')
    os.makedirs(folder, exist_ok=True)
    return folder


def calendar_folder(user_name):
    folder = os.path.join(notes_folder(), user_name, 'Calendar')
    os.makedirs(folder, exist_ok=True)
    return folder


def _clean_title(content, max_len=40):
    first_line = (content or '').strip().split('\n')[0]
    # Strip markdown syntax and characters unsafe in filenames
    title = re.sub(r'[#*`>\[\]()!_~]', '', first_line)
    title = re.sub(r'[^A-Za-z0-9 \-]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()[:max_len]
    title = title.rstrip(' -')
    return title or 'Note'


def make_filename(folder, created_at, content):
    date = (created_at or '')[:10]
    base = f'{date} {_clean_title(content)}'
    filename = f'{base}.md'
    n = 2
    while os.path.exists(os.path.join(folder, filename)):
        filename = f'{base} {n}.md'
        n += 1
    return filename


def _frontmatter(note, user_name):
    tags = note.get('tags', [])
    tag_names = ', '.join(t['name'] for t in tags)
    tag_colors = ', '.join(f'{t["name"]}: "{t["color"]}"' for t in tags)
    return (
        '---\n'
        f'id: {note["id"]}\n'
        f'user: {user_name}\n'
        f'feed: {note["feed"]}\n'
        f'tags: [{tag_names}]\n'
        f'tag_colors: {{{tag_colors}}}\n'
        f'source: {note["source"]}\n'
        f'pinned: {"true" if note["pinned"] else "false"}\n'
        f'archived: {"true" if note.get("archived") else "false"}\n'
        f'hidden: {"true" if note.get("hidden") else "false"}\n'
        f'created: {note["created_at"]}\n'
        f'updated: {note["updated_at"]}\n'
        '---\n'
    )


def _note_body(note):
    body = note.get('content', '') or ''
    todos = note.get('todos') or []
    if todos:
        lines = [
            '  ' * int(t.get('indent') or 0)
            + f'- [{"x" if t["checked"] else " "}] {t["text"]}'
            + (f' 📅 {t["due_at"]}' if t.get('due_at') else '')
            for t in todos]
        body = (body + '\n\n' if body.strip() else '') + '\n'.join(lines)
    replies = note.get('replies') or []
    if replies:
        lines = ['', '---', '', '## Replies', '']
        for r in replies:
            stamp = (r.get('created_at') or '')[:16].replace('T', ' ')
            lines.append(f'- **{r.get("user_name", "?")}** · {stamp} — {r["text"]}')
        body = body.rstrip() + '\n'.join(lines)
    return body


def write_note_file(note, user_name):
    """Write (or rewrite) the .md file for a note. Returns the filename."""
    try:
        folder = user_folder(user_name, note['feed'])
        filename = note.get('filename')
        if not filename:
            filename = make_filename(folder, note['created_at'], note['content'])
        path = os.path.join(folder, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(_frontmatter(note, user_name) + '\n' + _note_body(note) + '\n')
        return filename
    except OSError as e:
        log.warning('Could not write note file: %s', e)
        return note.get('filename')


def delete_note_file(note, user_name):
    if not note.get('filename'):
        return
    for feed in ('private', 'shared'):
        path = os.path.join(user_folder(user_name, feed), note['filename'])
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                log.warning('Could not delete note file %s: %s', path, e)


def move_note_file(note, user_name, old_feed):
    """Remove the file from the old feed folder; caller rewrites in the new one."""
    if not note.get('filename'):
        return
    old_path = os.path.join(user_folder(user_name, old_feed), note['filename'])
    if os.path.exists(old_path):
        try:
            os.remove(old_path)
        except OSError as e:
            log.warning('Could not move note file %s: %s', old_path, e)


# ── Calendar event stubs ─────────────────────────────────

NOTES_MARKER = '<!-- Notes added in Remndrs appear below this line. This file is safe to edit. -->'


def _event_frontmatter(event):
    lines = [
        '---',
        'type: calendar_event',
        f'event_uid: {event["uid"]}',
        f'calendar: {event["calendar_name"]}',
        f'title: {event["title"]}',
    ]
    if event.get('location'):
        lines.append(f'location: {event["location"]}')
    lines += [
        f'start: {event["start_at"]}',
        f'end: {event["end_at"]}',
        f'all_day: {"true" if event["all_day"] else "false"}',
        f'synced_at: {event["last_synced_at"]}',
    ]
    if event.get('deleted'):
        lines.append('deleted: true')
    lines.append('---')
    return '\n'.join(lines) + '\n'


def event_stub_filename(folder, event):
    date = (event['start_at'] or '')[:10]
    base = f'{date} {_clean_title(event["title"])}'
    filename = f'{base}.md'
    n = 2
    while os.path.exists(os.path.join(folder, filename)):
        filename = f'{base} {n}.md'
        n += 1
    return filename


def write_event_stub(event, user_name, existing_filename=None, extra_content=None):
    """Write or update the .md stub for a calendar event.

    Frontmatter is regenerated; content below the marker is preserved.
    Returns the filename.
    """
    try:
        folder = calendar_folder(user_name)
        filename = existing_filename
        preserved = ''
        if filename and os.path.exists(os.path.join(folder, filename)):
            with open(os.path.join(folder, filename), encoding='utf-8') as f:
                text = f.read()
            if NOTES_MARKER in text:
                preserved = text.split(NOTES_MARKER, 1)[1].lstrip('\n')
        if not filename:
            filename = event_stub_filename(folder, event)
        if extra_content:
            preserved = (preserved.rstrip() + '\n\n' if preserved.strip() else '') + extra_content
        with open(os.path.join(folder, filename), 'w', encoding='utf-8') as f:
            f.write(_event_frontmatter(event) + '\n' + NOTES_MARKER + '\n\n' + preserved)
        return filename
    except OSError as e:
        log.warning('Could not write event stub: %s', e)
        return existing_filename
