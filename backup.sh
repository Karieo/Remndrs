#!/bin/bash
# Remndrs off-box backup — copies BOTH the notes folder and the SQLite index
# to another machine over SSH. Designed for an always-on Pi whose only copy
# of your data otherwise lives on a single SD card.
#
# What it backs up:
#   • $NOTES_FOLDER          → $BACKUP_DEST/notes/   (the .md files: content)
#   • data/remndrs.db        → $BACKUP_DEST/db/      (the index: tags, todos,
#                                                     reminder schedules, shares)
#
# The DB is snapshotted with SQLite's online-backup API first, so it's a
# consistent copy even while the app is mid-write. DB snapshots are dated and
# rotated; notes are mirrored without --delete so a deletion on the Pi never
# wipes the backup copy.
#
# Configure in .env (or the environment):
#   BACKUP_DEST=user@host:path     e.g. clay@macbook.local:RemndrsBackup   (required)
#   BACKUP_SSH_KEY=~/.ssh/id_ed25519   private key for unattended cron      (optional)
#   BACKUP_KEEP_DB=14              how many dated DB snapshots to keep       (optional)
#
# Run by hand to test, then from cron (see PI_SETUP.md → "Backing up the Pi").
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
note()  { printf '  \033[33m•\033[0m %s\n' "$*"; }
fail()  { printf '  \033[31m✗ %s\033[0m\n' "$*"; exit 1; }

env_value() { grep "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2-; }
expand()    { eval echo "$1"; }   # expand a leading ~ in a path

PYTHON="$APP_DIR/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)" || fail "python3 not found"

# ── Config ───────────────────────────────────────────────
[ -f .env ] || fail "No .env found in $APP_DIR — run this on the Pi where Remndrs lives"

BACKUP_DEST="${BACKUP_DEST:-$(env_value BACKUP_DEST)}"
[ -n "$BACKUP_DEST" ] || fail "Set BACKUP_DEST in .env, e.g. BACKUP_DEST=clay@macbook.local:RemndrsBackup"
case "$BACKUP_DEST" in
  *:*) : ;;  # user@host:path
  *)   fail "BACKUP_DEST must be remote (user@host:path), got '$BACKUP_DEST'" ;;
esac

BACKUP_SSH_KEY="${BACKUP_SSH_KEY:-$(env_value BACKUP_SSH_KEY)}"
BACKUP_KEEP_DB="${BACKUP_KEEP_DB:-$(env_value BACKUP_KEEP_DB)}"
BACKUP_KEEP_DB="${BACKUP_KEEP_DB:-14}"

NOTES_FOLDER="$(expand "$(env_value NOTES_FOLDER)")"
[ -n "$NOTES_FOLDER" ] || fail "NOTES_FOLDER is not set in .env"
[ -d "$NOTES_FOLDER" ] || fail "Notes folder does not exist: $NOTES_FOLDER"

DB_PATH="$APP_DIR/data/remndrs.db"

SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new"
[ -n "$BACKUP_SSH_KEY" ] && SSH_OPTS="$SSH_OPTS -i $(expand "$BACKUP_SSH_KEY")"
SSH_CMD="ssh $SSH_OPTS"

DEST_HOST="${BACKUP_DEST%%:*}"
DEST_PATH="${BACKUP_DEST#*:}"

bold "── Remndrs backup → $BACKUP_DEST ──"

# ── 1 · Make sure the remote folders exist ───────────────
$SSH_CMD "$DEST_HOST" "mkdir -p '$DEST_PATH/notes' '$DEST_PATH/db'" \
  || fail "Can't reach $DEST_HOST over SSH — check the host, your key, and that Remote Login is on"
ok "Reached $DEST_HOST"

# ── 2 · Consistent DB snapshot, then ship it ─────────────
STAMP="$(date +%Y%m%d-%H%M%S)"
SNAP="$(mktemp -t "remndrs-XXXX").db"
trap 'rm -f "$SNAP"' EXIT
if [ -f "$DB_PATH" ]; then
  "$PYTHON" - "$DB_PATH" "$SNAP" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect(src); d = sqlite3.connect(dst)
with d:
    s.backup(d)
s.close(); d.close()
PY
  rsync -az -e "$SSH_CMD" "$SNAP" "$BACKUP_DEST/db/remndrs-$STAMP.db"
  ok "DB snapshot → db/remndrs-$STAMP.db"
else
  note "No data/remndrs.db yet — skipping DB snapshot"
fi

# ── 3 · Mirror the notes folder (no --delete: never lose backed-up files) ──
rsync -az -e "$SSH_CMD" "$NOTES_FOLDER/" "$BACKUP_DEST/notes/"
ok "Notes mirrored → notes/"

# ── 4 · Rotate old DB snapshots ──────────────────────────
$SSH_CMD "$DEST_HOST" \
  "cd '$DEST_PATH/db' && ls -1t remndrs-*.db 2>/dev/null | tail -n +$((BACKUP_KEEP_DB + 1)) | xargs -r rm -f"
ok "Kept newest $BACKUP_KEEP_DB DB snapshots"

bold ""
bold "Backup complete."
