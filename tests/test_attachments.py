"""Tier 2 — attachment handling (attachments.py).

Extension parsing, the allow-list gate (the security-relevant bit), markdown
link formatting, and path-traversal-safe resolution.
"""

import os

import pytest

import attachments
import database as db


# ── _extension (pure) ──────────────────────────────────────────────────────

def test_extension_lowercases():
    assert attachments._extension('Photo.JPG') == 'jpg'


def test_extension_uses_last_dot():
    assert attachments._extension('archive.tar.gz') == 'gz'


def test_extension_no_dot():
    assert attachments._extension('README') == ''


# ── markdown_link (pure) ───────────────────────────────────────────────────

def test_markdown_link_image_embeds():
    assert attachments.markdown_link('x.png').startswith('![')


def test_markdown_link_audio_video_document():
    assert '🎵' in attachments.markdown_link('memo.mp3')
    assert '🎬' in attachments.markdown_link('clip.mov')
    assert '📄' in attachments.markdown_link('report.pdf')


# ── save (allow-list gate) ─────────────────────────────────────────────────

def test_save_rejects_disallowed_extension(make_user, monkeypatch, tmp_path):
    monkeypatch.setenv('NOTES_FOLDER', str(tmp_path / 'notes'))
    user = make_user('Clay')
    note = db.create_note(user['id'], content='x')
    with pytest.raises(ValueError):
        attachments.save(b'#!/bin/sh', 'evil.sh', note['id'], user)


def test_save_stores_allowed_file_and_records_row(make_user, monkeypatch, tmp_path):
    monkeypatch.setenv('NOTES_FOLDER', str(tmp_path / 'notes'))
    user = make_user('Clay')
    note = db.create_note(user['id'], content='x')
    saved = attachments.save(b'hello', 'notes.txt', note['id'], user,
                            mime_type='text/plain')
    assert saved.endswith('.txt')
    path = os.path.join(attachments.files.attachments_folder('Clay'), saved)
    assert os.path.exists(path)
    assert db.get_attachment_by_filename(saved) is not None


def test_save_normalises_jpeg_to_jpg(make_user, monkeypatch, tmp_path):
    monkeypatch.setenv('NOTES_FOLDER', str(tmp_path / 'notes'))
    user = make_user('Clay')
    note = db.create_note(user['id'], content='x')
    saved = attachments.save(b'\xff\xd8', 'pic.jpeg', note['id'], user)
    assert saved.endswith('.jpg')


# ── resolve_path (traversal safety) ────────────────────────────────────────

def test_resolve_path_strips_directory_components(make_user, monkeypatch, tmp_path):
    monkeypatch.setenv('NOTES_FOLDER', str(tmp_path / 'notes'))
    user = make_user('Clay')
    note = db.create_note(user['id'], content='x')
    saved = attachments.save(b'data', 'doc.txt', note['id'], user)
    # A traversal attempt resolves only by basename within the user's folder.
    assert attachments.resolve_path('../../etc/' + saved, 'Clay') is not None
    assert attachments.resolve_path('/etc/passwd', 'Clay') is None
