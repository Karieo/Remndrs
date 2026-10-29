# Remndrs backup and recovery

`backup.sh` runs on the host containing the data, not inside the container.
It copies a verified SQLite snapshot and the entire notes tree to an SSH host.
Persistent attachments are under `<notes>/<user>/attachments` and are included.
The `uploads` directory is transient recording staging, not the persistent
attachment store. No `.env`, API credentials, or encryption keys are uploaded.

## Configuration

Values can come from the environment or `.env` (environment wins). `.env` is
read as literal values, not sourced or evaluated. Optional keys may be absent.

- `BACKUP_DEST=user@host:path` is required. Remote paths may contain letters,
  numbers, `_`, `.`, `/`, `-`; spaces and shell syntax are rejected. Use an SSH
  config host alias for unusual host syntax such as IPv6.
- `BACKUP_KEEP_DB=14` defaults to 14; allowed range 1–9999.
- `BACKUP_SSH_KEY=~/path/to/key` is optional. Existing SSH configuration and
  known-host behavior otherwise apply. Provision and verify the remote host
  key privately before scheduling; the script uses `accept-new`, not disabled
  host-key checks.
- `BACKUP_LAYOUT=auto` selects a layout only when exactly one expected database
  exists. `native` means `data/remndrs.db` plus `NOTES_FOLDER`; `docker` means
  host `data/db/remndrs.db` plus host `data/notes`, matching committed Compose.
  The Docker layout deliberately ignores container-only `NOTES_FOLDER=/app/notes`.
- If both databases exist, explicitly choose the correct layout. Do not guess
  from timestamps or delete the other data to satisfy detection.
- For custom mounts or a native runtime that used the fallback notes folder,
  set **both** `BACKUP_DB_PATH` and `BACKUP_NOTES_FOLDER` to the verified host
  paths. These paired paths override layout selection. Missing files fail;
  the script never creates a blank DB or claims success after skipping it.
- Native `NOTES_FOLDER` must point to the actual directory. The application may
  have fallen back to `~/Documents/Remndrs` if iCloud was unavailable; the backup
  intentionally does not guess which directory contains the current records.

Example for the committed Docker host layout (configure private destination
separately; do not paste credentials into chat):

```sh
BACKUP_LAYOUT=docker ./backup.sh
```

A success means SQLite integrity check passed and both transfers finished.
Any failure is nonzero with a visible `backup FAILED` message. Monitor cron's
exit status/logs; merely installing a cron entry is not verification. Repeated
runs preserve removed note/attachment files (`rsync` does not use `--delete`)
and retain only the configured number of DB snapshots. Notes are a cumulative
mirror, not per-snapshot versions: older DB snapshots can reference later
versions of an edited note file. For a strict point-in-time recovery, quiesce
application writes and inbound processing during a manually authorized backup,
or use a filesystem snapshot workflow. This script does not stop services.

## Private recovery material

Keep `ENCRYPTION_KEY` and required integration configuration in a separate,
protected credential backup. Without the original encryption key, saved CalDAV
credentials cannot be decrypted. A database snapshot also contains sensitive
notes, password hashes and credential ciphertext; restrict backup destination
permissions and use encrypted storage where appropriate. Never post these
values in a report. The script does not claim to provide at-rest encryption.

## Restore drill (new empty directory, never over live data)

1. Pick a completed snapshot and copy it plus the backed-up `notes/` tree into
   a **new isolated restore directory**. Retain the original source and backup.
2. Open that copied DB read-only and run `PRAGMA integrity_check`; require `ok`.
   Verify expected users, note ownership/private/shared flags, note contents,
   reminder ownership and scheduled times, and attachment metadata. Compare
   representative Markdown and attachment bytes to their known test fixtures.
3. Start any test application only against the restored paths, with outbound
   SMS/email/push/calendar integrations disabled and no production environment
   loaded. Never let a restore drill fire real scheduled reminders.
4. Actual replacement of a live database/notes tree requires separate approval:
   stop writes first, retain a rollback copy of all existing data, restore both
   DB and notes to the deployment's host paths, preserve permissions, then
   privately validate before restoring inbound traffic. Do not overlay a DB
   while its old `-wal`/`-shm` files are active.

The automated `tests/test_backup.py` drill uses synthetic data and fake local
SSH/rsync: it verifies owner/private-note/reminder metadata, SQLite integrity,
Markdown and attachment bytes in a new restored directory, missing/ambiguous
paths, optional keys, retention, transfer errors and non-evaluation of config.
It does **not** prove the real host schedule, SSH credentials, remote storage,
network transfer, encryption-key recovery or production restore is working.
