#!/bin/bash
# Remndrs one-command installer for macOS.
set -e

cd "$(dirname "$0")"

echo "── Remndrs setup ──"

# 1. Python dependencies (user install — no venv needed for a single local app)
echo "Installing Python dependencies…"
python3 -m pip install --user -r requirements.txt

# 2. .env
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit it to add your credentials."
fi

# 3. Session secret
if grep -q '^SESSION_SECRET=replace-with-long-random-string' .env || ! grep -q '^SESSION_SECRET=.\+' .env; then
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i '' "s|^SESSION_SECRET=.*|SESSION_SECRET=${SECRET}|" .env 2>/dev/null || \
    sed -i "s|^SESSION_SECRET=.*|SESSION_SECRET=${SECRET}|" .env
  echo "Generated SESSION_SECRET."
fi

# 4. Encryption key for CalDAV credentials
if ! grep -q '^ENCRYPTION_KEY=.\+' .env; then
  KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  if grep -q '^ENCRYPTION_KEY=' .env; then
    sed -i '' "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${KEY}|" .env 2>/dev/null || \
      sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${KEY}|" .env
  else
    echo "ENCRYPTION_KEY=${KEY}" >> .env
  fi
  echo "Generated ENCRYPTION_KEY."
fi

# 5. launchd auto-start on login
PLIST_SRC="com.remndrs.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.remndrs.plist"
mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__APP_DIR__|$(pwd)|g; s|__PYTHON__|$(command -v python3)|g" "$PLIST_SRC" > "$PLIST_DEST"
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"
echo "Installed launchd agent — Remndrs will start automatically on login."

echo ""
echo "Done. Start now with:  python3 app.py"
echo "Then open http://localhost:3000"
echo "See CLOUDFLARE_SETUP.md to make it reachable from your phone."
