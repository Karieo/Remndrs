#!/bin/bash
# Remndrs one-line installer:
#   curl -fsSL https://raw.githubusercontent.com/Karieo/Remndrs/main/install.sh | bash
# Clones (or updates) the app into ~/remndrs and runs the setup.
set -euo pipefail

REPO="https://github.com/Karieo/Remndrs.git"
DIR="$HOME/remndrs"

if ! command -v git >/dev/null 2>&1; then
  echo "git not found — install Apple's Command Line Tools first:"
  echo "  xcode-select --install"
  exit 1
fi

if [ -d "$DIR/.git" ]; then
  echo "Updating existing install in $DIR…"
  git -C "$DIR" pull --ff-only
else
  echo "Installing Remndrs into $DIR…"
  git clone "$REPO" "$DIR"
fi

# Hand off to the real installer, attached to the terminal so it can
# prompt for the owner account even when this script came in via a pipe.
exec bash "$DIR/setup.sh" < /dev/tty
