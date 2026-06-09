"""Saves any inbound file (MMS, email, web upload) to iCloud and links it from notes."""

import os
import uuid
from datetime import date

import database as db
import files

ALLOWED_EXTENSIONS = {
    # Images
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic',
    # Documents
    'pdf', 'doc', 'docx', 'txt', 'md', 'csv', 'xlsx', 'xls', 'pptx',
    # Audio
    'm4a', 'mp3', 'wav', 'ogg', 'webm', 'aac',
    # Video
    'mp4', 'mov',
    # Archives
    'zip',
}

IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic'}
AUDIO_EXTS = {'m4a', 'mp3', 'wav', 'ogg', 'webm', 'aac'}
VIDEO_EXTS = {'mp4', 'mov'}


def _extension(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def save(content: bytes, original_filename: str, note_id: str, user: dict,
         mime_type: str = None) -> str:
    """Save file bytes to the user's iCloud attachments folder.

    Returns the saved filename. Raises ValueError on disallowed extension.
    """
    ext = _extension(original_filename)
    if ext == 'jpeg':
        ext = 'jpg'
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f'File type .{ext} is not allowed')

    safe_base = os.path.basename(original_filename).rsplit('.', 1)[0][:60] or 'file'
    saved_filename = f'{date.today().isoformat()}-{uuid.uuid4().hex[:6]}-{safe_base}.{ext}'
    folder = files.attachments_folder(user['name'])
    with open(os.path.join(folder, saved_filename), 'wb') as f:
        f.write(content)

    db.add_attachment(note_id, original_filename, saved_filename,
                      mime_type or '', len(content))
    return saved_filename


def markdown_link(saved_filename: str) -> str:
    ext = _extension(saved_filename)
    url = f'/api/attachments/{saved_filename}'
    if ext in IMAGE_EXTS:
        return f'![{saved_filename}]({url})'
    if ext in AUDIO_EXTS:
        return f'[🎵 {saved_filename}]({url})'
    if ext in VIDEO_EXTS:
        return f'[🎬 {saved_filename}]({url})'
    return f'[📄 {saved_filename}]({url})'


def resolve_path(saved_filename: str, user_name: str):
    """Return the absolute path for an attachment if it exists, else None."""
    path = os.path.join(files.attachments_folder(user_name),
                        os.path.basename(saved_filename))
    return path if os.path.exists(path) else None
