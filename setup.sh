#!/bin/bash
# Remndrs installer — sets up everything on a Mac in one run.
# Safe to re-run any time (updates deps, keeps your .env and data).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
note()  { printf '  \033[33m•\033[0m %s\n' "$*"; }
fail()  { printf '  \033[31m✗ %s\033[0m\n' "$*"; exit 1; }

IS_MAC=false
[ "$(uname)" = "Darwin" ] && IS_MAC=true

bold "── Remndrs install ──"

# 1 · Python ──────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  if $IS_MAC; then
    note "Python 3 not found — triggering the Command Line Tools installer."
    note "Re-run this script when it finishes."
    xcode-select --install || true
    exit 1
  fi
  fail "python3 is required"
fi
ok "Python $(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"

# 2 · Virtualenv + dependencies ───────────────────────────
# A venv avoids the 'externally-managed-environment' error on modern Macs.
if [ ! -x "venv/bin/python" ]; then
  python3 -m venv venv
  ok "Created virtualenv"
fi
./venv/bin/pip -q install --upgrade pip
./venv/bin/pip -q install -r requirements.txt
ok "Dependencies installed"
PYTHON="$APP_DIR/venv/bin/python"

# 3 · .env ────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  ok "Created .env from .env.example"
fi

set_env() {  # set_env KEY VALUE — replace or append, value untouched
  local key="$1" value="$2"
  if grep -q "^${key}=" .env; then
    "$PYTHON" - "$key" "$value" <<'PYEOF'
import sys, pathlib
key, value = sys.argv[1], sys.argv[2]
p = pathlib.Path('.env')
lines = p.read_text().splitlines()
lines = [f'{key}={value}' if l.startswith(f'{key}=') else l for l in lines]
p.write_text('\n'.join(lines) + '\n')
PYEOF
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

env_value() { grep "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2-; }

if [ -z "$(env_value SESSION_SECRET)" ] || [ "$(env_value SESSION_SECRET)" = "replace-with-long-random-string" ]; then
  set_env SESSION_SECRET "$("$PYTHON" -c 'import secrets; print(secrets.token_hex(32))')"
  ok "Generated SESSION_SECRET"
fi
if [ -z "$(env_value ENCRYPTION_KEY)" ]; then
  set_env ENCRYPTION_KEY "$("$PYTHON" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
  ok "Generated ENCRYPTION_KEY"
fi

# 4 · Owner account (first run only, interactive only) ────
if [ ! -f data/remndrs.db ] && [ -t 0 ]; then
  current_name="$(env_value OWNER_NAME)"
  current_pw="$(env_value OWNER_PASSWORD)"
  if [ -z "$current_name" ] || [ "$current_pw" = "changeme" ] || [ -z "$current_pw" ]; then
    bold ""
    bold "Set up your account (stored in .env, used to seed the database):"
    read -r -p "  Your name [${current_name:-Clay}]: " owner_name
    owner_name="${owner_name:-${current_name:-Clay}}"
    read -r -s -p "  Password: " owner_pw; echo
    [ -n "$owner_pw" ] || fail "Password can't be empty"
    set_env OWNER_NAME "$owner_name"
    set_env OWNER_PASSWORD "$owner_pw"
    ok "Owner account configured"
  fi
fi

# 5 · launchd auto-start (Mac only) ───────────────────────
if $IS_MAC; then
  PLIST_DEST="$HOME/Library/LaunchAgents/com.remndrs.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  sed "s|__APP_DIR__|$APP_DIR|g; s|__PYTHON__|$PYTHON|g" com.remndrs.plist > "$PLIST_DEST"
  launchctl unload "$PLIST_DEST" 2>/dev/null || true
  launchctl load "$PLIST_DEST"
  ok "Auto-start installed (launchd) — Remndrs starts when you log in"

  # 6 · Wait for the server, then open the browser ─────────
  PORT="$(env_value PORT)"; PORT="${PORT:-3000}"
  printf '  … starting'
  for _ in $(seq 1 20); do
    if curl -s -o /dev/null "http://localhost:$PORT/login"; then
      echo
      ok "Remndrs is running"
      open "http://localhost:$PORT"
      break
    fi
    printf '.'
    sleep 1
  done
  echo
else
  note "Not macOS — skipped launchd auto-start. Run with: $PYTHON app.py"
fi

bold ""
bold "Done."
echo "  App:        http://localhost:${PORT:-3000}"
echo "  Logs:       /tmp/remndrs.log  ·  /tmp/remndrs.err.log"
echo "  Notes:      $(env_value NOTES_FOLDER | sed "s|^~|$HOME|")"
echo "  Integrations (Twilio / OpenAI / Mailgun / CalDAV): edit .env, then"
echo "  re-run ./setup.sh — see README.md for each provider's steps."
echo "  Phone access from anywhere: see CLOUDFLARE_SETUP.md"
