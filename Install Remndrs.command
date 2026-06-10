#!/bin/bash
# Double-click this file in Finder to install (or update) Remndrs.
# macOS opens .command files in Terminal automatically.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$DIR/setup.sh" ]; then
  # Running from inside a downloaded/cloned copy of the repo.
  exec bash "$DIR/setup.sh"
fi

# Otherwise bootstrap from GitHub.
exec bash -c "$(curl -fsSL https://raw.githubusercontent.com/Karieo/Remndrs/main/install.sh)"
