#!/bin/bash
# SessionStart hook: install Python dependencies so tests can run in
# Claude Code on the web sessions (the container is cloned fresh each time).
set -euo pipefail

# Only needed in the remote (web) environment; local machines already have deps.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# requirements-dev.txt pulls in requirements.txt plus pytest/pytest-cov.
# --ignore-installed sidesteps a system blinker package that lacks a RECORD file.
python3 -m pip install -q --ignore-installed blinker -r requirements-dev.txt
