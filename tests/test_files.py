"""Tier 2 — markdown file mirroring (files.py).

Covers the pure formatting/sanitizing helpers plus the two stateful bits most
likely to silently corrupt data: filename collision handling and the
``NOTES_MARKER`` content-preservation in calendar event stubs.
"""

import os

import files


# ── _clean_title (pure) ────────────────────────────────────────────────────

def test_clean_title_strips_markdown_and_unsafe_chars():
    assert files._clean_title('# Hello *world*!') == 'Hello world'


def test_clean_title_falls_back_to_note_when_empty():
    assert files._clean_title('') == 'Note'
    assert files._clean_title('***') == 'Note'
    assert files._clean_title('🎉🎉') == 'Note'


def test_clean_title_uses_first_line_only_and_truncates():
    assert files._clean_title('first line\nsecond line') == 'first line'
    assert len(files._clean_title('x' * 100)) <= 40


def test_clean_title_trims_trailing_hyphen_space():
    assert files._clean_title('todo - ') == 'todo'


# ── _frontmatter / _note_body (pure) ───────────────────────────────────────

def _note(**over):
    base = {'id': 'n1', 'feed': 'private', 'source': 'web', 'pinned': False,
            'archived': False, 'created_at': '2026-06-13T09:00:00',
            'updated_at': '2026-06-13T09:00:00', 'content': 'body text',
            'tags': []}
    base.update(over)
    return base


def test_frontmatter_includes_core_fields():
    fm = files._frontmatter(_note(tags=[{'name': 'WORK', 'color': '#abc'}]), 'Clay')
    assert 'id: n1' in fm
    assert 'user: Clay' in fm
    assert 'feed: private' in fm
    assert 'tags: [WORK]' in fm
    assert 'WORK: "#abc"' in fm
    assert 'pinned: false' in fm


def test_note_body_renders_todos_as_checkboxes():
    body = files._note_body(_note(content='List', todos=[
        {'text': 'done', 'checked': True},
        {'text': 'todo', 'checked': False}]))
    assert '- [x] done' in body
    assert '- [ ] todo' in body


def test_note_body_renders_replies_section():
    body = files._note_body(_note(replies=[
        {'user_name': 'Sam', 'created_at': '2026-06-13T09:30:00', 'text': 'ok!'}]))
    assert '## Replies' in body
    assert '**Sam**' in body
    assert '2026-06-13 09:30' in body
    assert 'ok!' in body


# ── make_filename (collision handling) ─────────────────────────────────────

def test_make_filename_basic(tmp_path):
    name = files.make_filename(str(tmp_path), '2026-06-13T09:00:00', 'Buy milk')
    assert name == '2026-06-13 Buy milk.md'


def test_make_filename_collision_increments(tmp_path):
    first = files.make_filename(str(tmp_path), '2026-06-13T09:00:00', 'Buy milk')
    (tmp_path / first).write_text('x')
    second = files.make_filename(str(tmp_path), '2026-06-13T09:00:00', 'Buy milk')
    assert second == '2026-06-13 Buy milk 2.md'
    (tmp_path / second).write_text('x')
    third = files.make_filename(str(tmp_path), '2026-06-13T09:00:00', 'Buy milk')
    assert third == '2026-06-13 Buy milk 3.md'


# ── write_note_file round-trip ─────────────────────────────────────────────

def test_write_note_file_creates_file(tmp_path, monkeypatch):
    monkeypatch.setenv('NOTES_FOLDER', str(tmp_path / 'notes'))
    note = _note(content='hello world', filename=None)
    fname = files.write_note_file(note, 'Clay')
    assert fname.endswith('.md')
    path = os.path.join(files.user_folder('Clay', 'private'), fname)
    text = open(path, encoding='utf-8').read()
    assert 'hello world' in text
    assert 'id: n1' in text


# ── calendar event stub marker preservation ────────────────────────────────

def _event(**over):
    base = {'uid': 'evt-1', 'calendar_name': 'Home', 'title': 'Dentist',
            'location': '', 'start_at': '2026-06-20T10:00:00',
            'end_at': '2026-06-20T11:00:00', 'all_day': False,
            'last_synced_at': '2026-06-13T09:00:00'}
    base.update(over)
    return base


def test_event_stub_preserves_user_content_below_marker(tmp_path, monkeypatch):
    monkeypatch.setenv('NOTES_FOLDER', str(tmp_path / 'notes'))
    fname = files.write_event_stub(_event(), 'Clay')
    path = os.path.join(files.calendar_folder('Clay'), fname)

    # User appends their own notes below the safe-to-edit marker.
    text = open(path, encoding='utf-8').read()
    open(path, 'w', encoding='utf-8').write(text + '\nMy private prep notes\n')

    # A re-sync (title changed) regenerates frontmatter but must keep the notes.
    files.write_event_stub(_event(title='Dentist (rescheduled)'), 'Clay',
                          existing_filename=fname)
    updated = open(path, encoding='utf-8').read()
    assert 'My private prep notes' in updated
    assert 'Dentist (rescheduled)' in updated


def test_event_frontmatter_marks_deleted(tmp_path):
    fm = files._event_frontmatter(_event(deleted=True))
    assert 'deleted: true' in fm
    assert files._event_frontmatter(_event()).find('deleted:') == -1
