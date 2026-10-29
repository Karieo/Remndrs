#!/bin/bash
# Remndrs off-box backup. See BACKUP_RECOVERY.md for layouts and restore checks.
# Backs up SQLite plus the entire notes tree (including persistent attachments).
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
SNAP=''
cleanup() {
  status=$?
  [ -z "$SNAP" ] || rm -f "$SNAP"
  if [ "$status" -ne 0 ]; then
    printf 'Remndrs backup FAILED (exit %s); do not treat this run as recoverable.\n' "$status" >&2
  fi
}
trap cleanup EXIT
fail() { printf 'Remndrs backup: %s\n' "$*" >&2; exit 1; }
# Never source/eval .env. Missing optional keys must return success under pipefail.
env_value() {
  local line=''
  line="$(grep "^$1=" .env 2>/dev/null | head -1)" || true
  printf '%s' "${line#*=}"
}
expand() { printf '%s' "${1/#\~/$HOME}"; }
config() {
  local value="${!1:-}"
  [ -n "$value" ] || value="$(env_value "$1")"
  # Support conventional whole-value .env quoting, without shell evaluation.
  if [[ "$value" == \"*\" && ${#value} -ge 2 ]] || [[ "$value" == \'*\' && ${#value} -ge 2 ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}
PYTHON="$APP_DIR/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)" || fail 'python3 not found'
BACKUP_DEST="$(config BACKUP_DEST)"
[ -n "$BACKUP_DEST" ] || fail 'Set BACKUP_DEST=user@host:path'
[[ "$BACKUP_DEST" == *:* ]] || fail 'BACKUP_DEST must be remote (user@host:path)'
DEST_HOST="${BACKUP_DEST%%:*}"
DEST_PATH="${BACKUP_DEST#*:}"
# Deliberately narrow remote-shell grammar; reject rather than interpolate shell syntax.
[[ "$DEST_HOST" =~ ^[A-Za-z0-9_][A-Za-z0-9_.@-]*$ ]] || fail 'Invalid backup SSH host'
[[ "$DEST_PATH" =~ ^[A-Za-z0-9_./-]+$ && "$DEST_PATH" != -* && "$DEST_PATH" != / ]] || fail 'Backup remote path must be non-root, with no spaces or shell characters'
BACKUP_KEEP_DB="$(config BACKUP_KEEP_DB)"
BACKUP_KEEP_DB="${BACKUP_KEEP_DB:-14}"
[[ "$BACKUP_KEEP_DB" =~ ^[1-9][0-9]{0,3}$ ]] || fail 'BACKUP_KEEP_DB must be an integer from 1 to 9999'
DB_PATH="$(config BACKUP_DB_PATH)"
NOTES_FOLDER="$(config BACKUP_NOTES_FOLDER)"
if [ -n "$DB_PATH" ] || [ -n "$NOTES_FOLDER" ]; then
  [ -n "$DB_PATH" ] && [ -n "$NOTES_FOLDER" ] || fail 'Set BOTH BACKUP_DB_PATH and BACKUP_NOTES_FOLDER for custom paths'
else
  LAYOUT="$(config BACKUP_LAYOUT)"
  LAYOUT="${LAYOUT:-auto}"
  if [ "$LAYOUT" = auto ]; then
    native=0; docker=0
    [ ! -f data/remndrs.db ] || native=1
    [ ! -f data/db/remndrs.db ] || docker=1
    [ "$((native + docker))" -eq 1 ] || fail 'Cannot select one database; set BACKUP_LAYOUT=native or docker, or both explicit backup paths'
    if [ "$docker" -eq 1 ]; then LAYOUT=docker; else LAYOUT=native; fi
  fi
  case "$LAYOUT" in
    docker) DB_PATH="$APP_DIR/data/db/remndrs.db"; NOTES_FOLDER="$APP_DIR/data/notes" ;;
    native) DB_PATH="$APP_DIR/data/remndrs.db"; NOTES_FOLDER="$(config NOTES_FOLDER)"
            [ -n "$NOTES_FOLDER" ] || fail 'Native backup needs NOTES_FOLDER (or both explicit backup paths)' ;;
    *) fail 'BACKUP_LAYOUT must be auto, native, or docker' ;;
  esac
fi
DB_PATH="$(expand "$DB_PATH")"
NOTES_FOLDER="$(expand "$NOTES_FOLDER")"
[ -f "$DB_PATH" ] || fail 'Configured database is missing; refusing an incomplete backup'
[ -d "$NOTES_FOLDER" ] || fail 'Configured notes directory is missing; check runtime fallback or Docker host paths'
SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
SSH_CMD='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new'
KEY="$(config BACKUP_SSH_KEY)"
if [ -n "$KEY" ]; then
  KEY="$(expand "$KEY")"
  [[ "$KEY" != *"'"* && "$KEY" != *$'\n'* && "$KEY" != *$'\r'* ]] || fail 'SSH key path contains unsupported quote/newline'
  [ -f "$KEY" ] || fail 'Configured SSH key file is missing'
  SSH+=(-i "$KEY")
  SSH_CMD+=" -i '$KEY'"
fi
# mktemp returns the actual snapshot filename; no leaked extension-less file.
SNAP="$(mktemp "${TMPDIR:-/tmp}/remndrs-backup.XXXXXX")"
"$PYTHON" - "$DB_PATH" "$SNAP" <<'PY'
import pathlib, sqlite3, sys
src, dst = sys.argv[1:]
s = sqlite3.connect(pathlib.Path(src).resolve().as_uri() + '?mode=ro', uri=True)
d = sqlite3.connect(dst)
try:
    s.backup(d)
    if d.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise SystemExit('Backup database integrity check failed')
finally:
    d.close()
    s.close()
PY
STAMP="$(date +%Y%m%d-%H%M%S)-$$"
"${SSH[@]}" "$DEST_HOST" "mkdir -p '$DEST_PATH/notes' '$DEST_PATH/db'"
# No --delete: deletions in the app must not erase previous note/attachment copies.
rsync -az -e "$SSH_CMD" "$NOTES_FOLDER/" "$BACKUP_DEST/notes/"
rsync -az -e "$SSH_CMD" "$SNAP" "$BACKUP_DEST/db/remndrs-$STAMP.db"
"${SSH[@]}" "$DEST_HOST" \
  "cd '$DEST_PATH/db' && ls -1t remndrs-*.db | tail -n +$((BACKUP_KEEP_DB + 1)) | while IFS= read -r file; do rm -f -- \"\$file\" || exit 1; done"
printf 'Backup complete: verified SQLite snapshot and notes tree transferred; retained %s DB snapshots.\n' "$BACKUP_KEEP_DB"
