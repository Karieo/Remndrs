#!/bin/bash
# Remndrs uninstaller. Stops the app and removes auto-start.
# Your notes (iCloud .md files) are NEVER touched.
#   ./uninstall.sh           keep the app folder, database, and .env
#   ./uninstall.sh --purge   also delete the virtualenv, database, and .env
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.remndrs.plist"

if [ -f "$PLIST" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "✓ Auto-start removed and app stopped"
else
  echo "• No launchd agent found (app wasn't auto-starting)"
fi

if [ "${1:-}" = "--purge" ]; then
  rm -rf "$APP_DIR/venv" "$APP_DIR/data" "$APP_DIR/.env" "$APP_DIR/uploads"
  echo "✓ Removed virtualenv, database, .env, and uploads"
  echo "• The app folder itself and your notes in iCloud are untouched."
  echo "  Delete the folder with: rm -rf \"$APP_DIR\""
else
  echo "• Kept the app folder, database, and .env (re-run ./setup.sh to reinstall)"
  echo "  For a full wipe: ./uninstall.sh --purge"
fi
echo "• Your notes are safe — Remndrs never deletes the iCloud folder."
