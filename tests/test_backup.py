"""Backup shell contract: synthetic SQLite/files, fake local SSH/rsync only."""
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

import database as db

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def backup(tmp_path):
    app = tmp_path / 'app'
    app.mkdir()
    shutil.copy(REPO / 'backup.sh', app / 'backup.sh')
    remote = tmp_path / 'remote'
    bins = tmp_path / 'bin'
    bins.mkdir()
    # Only synthetic remote commands may execute; command includes our tmp root.
    (bins / 'ssh').write_text('''#!/usr/bin/env python3
import os, subprocess, sys
command = sys.argv[-1]
assert os.environ['TEST_REMOTE'] in command, 'not the synthetic destination'
if os.environ.get('FAIL_SSH'): sys.exit(17)
raise SystemExit(subprocess.run(['bash', '-c', command]).returncode)
''')
    (bins / 'rsync').write_text('''#!/usr/bin/env python3
import os, pathlib, shutil, sys
if os.environ.get('FAIL_RSYNC'): sys.exit(18)
src, dest = sys.argv[-2:]
assert dest.startswith('fixture@host:'), 'not a synthetic transfer'
dest = pathlib.Path(dest.split(':', 1)[1])
assert dest.is_relative_to(pathlib.Path(os.environ['TEST_REMOTE']))
if pathlib.Path(src).is_dir():
    shutil.copytree(src, dest, dirs_exist_ok=True)
else:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
''')
    for path in bins.iterdir():
        path.chmod(0o755)
    env = {'PATH': f'{bins}:{Path(sys.executable).parent}:/usr/bin:/bin',
           'HOME': str(tmp_path), 'TEST_REMOTE': str(remote),
           'TMPDIR': str(tmp_path), 'BACKUP_DEST': f'fixture@host:{remote}'}

    def prepare(layout='native'):
        dbfile = app / ('data/db/remndrs.db' if layout == 'docker' else 'data/remndrs.db')
        notes = app / ('data/notes' if layout == 'docker' else 'notes with spaces')
        dbfile.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(dbfile) as conn:
            conn.executescript(db.SCHEMA)
            conn.executescript("""
                INSERT INTO users (id,name,password_hash,created_at)
                  VALUES ('u1','SyntheticOwner','synthetic-hash','2026-01-01');
                INSERT INTO notes (id,user_id,content,feed,created_at,updated_at)
                  VALUES ('n1','u1','synthetic note','private','2026-01-01','2026-01-01');
                INSERT INTO reminders (id,user_id,note_id,message,fire_at,created_at)
                  VALUES ('r1','u1','n1','synthetic reminder','2030-01-01T12:00:00','2026-01-01');
                INSERT INTO attachments (id,note_id,original_filename,saved_filename,created_at)
                  VALUES ('a1','n1','picture.png','picture.png','2026-01-01');
            """)
        (notes / 'SyntheticOwner' / 'attachments').mkdir(parents=True, exist_ok=True)
        (notes / 'SyntheticOwner' / 'note.md').write_text('synthetic note')
        (notes / 'SyntheticOwner' / 'attachments' / 'picture.png').write_bytes(b'\x89PNG\r\nsynthetic')
        # Native .env quoting is deliberately supported; Docker must ignore this.
        (app / '.env').write_text(f'NOTES_FOLDER="{notes}"\n')
        return dbfile, notes

    def run(**settings):
        return subprocess.run(['bash', str(app / 'backup.sh')], cwd=app,
                              env={**env, **settings}, capture_output=True, text=True,
                              timeout=20)
    return app, remote, prepare, run


@pytest.mark.parametrize('layout', ['native', 'docker'])
def test_optional_settings_and_complete_synthetic_recovery(backup, tmp_path, layout):
    app, remote, prepare, run = backup
    _, notes = prepare(layout)
    if layout == 'docker':
        (app / '.env').write_text('NOTES_FOLDER=/app/notes\n')
    result = run()
    assert result.returncode == 0, result.stderr
    assert 'Backup complete' in result.stdout
    snapshots = list((remote / 'db').glob('remndrs-*.db'))
    assert len(snapshots) == 1
    # Recover into a new empty directory, never over live source data.
    restored = tmp_path / 'restored'
    restored.mkdir()
    shutil.copy(snapshots[0], restored / 'remndrs.db')
    shutil.copytree(remote / 'notes', restored / 'notes')
    with sqlite3.connect(restored / 'remndrs.db') as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert conn.execute('SELECT user_id,content,feed FROM notes').fetchone() == ('u1','synthetic note','private')
        assert conn.execute('SELECT user_id,note_id,fire_at FROM reminders').fetchone() == ('u1','n1','2030-01-01T12:00:00')
        assert conn.execute('SELECT name FROM users WHERE id="u1"').fetchone() == ('SyntheticOwner',)
        assert conn.execute('SELECT note_id,saved_filename FROM attachments').fetchone() == ('n1','picture.png')
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    assert (restored / 'notes/SyntheticOwner/note.md').read_text() == 'synthetic note'
    assert (restored / 'notes/SyntheticOwner/attachments/picture.png').read_bytes() == b'\x89PNG\r\nsynthetic'
    assert not list(tmp_path.glob('remndrs-backup.*'))


def test_ambiguous_database_requires_explicit_layout(backup):
    _, remote, prepare, run = backup
    prepare('native'); prepare('docker')
    result = run()
    assert result.returncode != 0 and 'Cannot select one database' in result.stderr
    assert not remote.exists()
    assert run(BACKUP_LAYOUT='docker').returncode == 0


def test_missing_database_is_failure_not_success(backup):
    _, remote, prepare, run = backup
    dbfile, _ = prepare()
    dbfile.unlink()
    result = run(BACKUP_LAYOUT='native')
    assert result.returncode != 0 and 'database is missing' in result.stderr
    assert 'Backup complete' not in result.stdout and not remote.exists()


def test_missing_notes_is_failure(backup):
    _, remote, prepare, run = backup
    _, notes = prepare()
    shutil.rmtree(notes)
    result = run()
    assert result.returncode != 0 and 'notes directory is missing' in result.stderr
    assert not remote.exists()


@pytest.mark.parametrize('value', ['0', '-1', 'abc', '1;touch injected', '10000'])
def test_invalid_retention_fails_before_transfer(backup, value):
    _, remote, prepare, run = backup
    prepare()
    result = run(BACKUP_KEEP_DB=value)
    assert result.returncode != 0 and 'BACKUP_KEEP_DB' in result.stderr
    assert not remote.exists()


def test_custom_paths_must_be_paired_and_do_not_evaluate_shell(backup):
    app, remote, prepare, run = backup
    dbfile, notes = prepare()
    assert run(BACKUP_DB_PATH=str(dbfile)).returncode != 0
    result = run(BACKUP_DB_PATH=str(dbfile), BACKUP_NOTES_FOLDER='$(touch injected)')
    assert result.returncode != 0
    assert not (app / 'injected').exists()
    assert run(BACKUP_DB_PATH=str(dbfile), BACKUP_NOTES_FOLDER=str(notes)).returncode == 0


@pytest.mark.parametrize('dest', ['-host:/tmp/test', "host:path' ; touch injected", 'host:/', 'host:path with spaces'])
def test_remote_shell_syntax_rejected(backup, dest):
    app, remote, prepare, run = backup
    prepare()
    assert run(BACKUP_DEST=dest).returncode != 0
    assert not (app / 'injected').exists() and not remote.exists()


@pytest.mark.parametrize('failure', ['FAIL_RSYNC', 'FAIL_SSH'])
def test_transfer_failure_is_loud_and_cleans_snapshot(backup, tmp_path, failure):
    _, _, prepare, run = backup
    prepare()
    result = run(**{failure: '1'})
    assert result.returncode != 0 and 'backup FAILED' in result.stderr
    assert 'Backup complete' not in result.stdout
    assert not list(tmp_path.glob('remndrs-backup.*'))


def test_corrupt_database_is_not_uploaded(backup):
    _, remote, prepare, run = backup
    dbfile, _ = prepare()
    dbfile.write_bytes(b'not sqlite')
    result = run()
    assert result.returncode != 0 and 'backup FAILED' in result.stderr
    assert not remote.exists()


def test_retention_and_no_delete_notes(backup):
    _, remote, prepare, run = backup
    _, notes = prepare()
    for _ in range(3):
        result = run(BACKUP_KEEP_DB='2')
        assert result.returncode == 0, result.stderr
    assert len(list((remote / 'db').glob('remndrs-*.db'))) == 2
    (notes / 'SyntheticOwner/note.md').unlink()
    assert run().returncode == 0
    assert (remote / 'notes/SyntheticOwner/note.md').exists()
