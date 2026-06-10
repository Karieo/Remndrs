# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Remndrs is a local-first personal notes/reminders app that runs on the user's Mac. Notes arrive via web UI, SMS (Twilio), email (Mailgun), or voice calls (Twilio + Whisper), and every note is also written as an Obsidian-compatible `.md` file to an iCloud Drive folder. The full product spec lives in the original handoff document; the README covers integration setup.

## Commands

```bash
pip install -r requirements.txt   # deps (or ./setup.sh for full Mac install)
python3 app.py                    # run — http://localhost:3000 (falls back to 3001/3002)
```

There is no test suite or linter configured. To smoke-test, run the app with throwaway env and hit the API:

```bash
OWNER_NAME=Clay OWNER_PASSWORD=test NOTES_FOLDER=/tmp/Remndrs PORT=3456 python3 app.py
curl -c /tmp/c.txt -X POST localhost:3456/api/auth/login -H 'Content-Type: application/json' -d '{"login":"Clay","password":"test"}'
```

The SQLite DB lives at `data/remndrs.db` (gitignored); delete it to reset. On first run with an empty users table, the owner account is seeded from `OWNER_NAME`/`OWNER_PASSWORD`.

## Architecture

**Stack:** Flask + stdlib `sqlite3` (FTS5) + APScheduler on the backend; vanilla JS + marked.js (CDN) on the frontend. No build step, no ORM, no frontend framework. Real-time updates use SSE, not WebSockets.

**Module layout** — `app.py` holds all HTTP routes and delegates to modules:

- `database.py` — schema (created idempotently on import via `init_db()`) and every query function. Opens a fresh connection per call, so it's safe from APScheduler threads. Full-text search works through `notes_fts` + triggers; note content only, not todo items.
- `files.py` — mirrors notes to `.md` files with YAML frontmatter. Private notes go to `{NOTES_FOLDER}/{UserName}/`, shared to `{NOTES_FOLDER}/Shared/`, calendar event stubs to `{UserName}/Calendar/`. Falls back to `~/Documents/Remndrs` when the iCloud path's parent doesn't exist.
- `sse.py` — per-user `queue.Queue` of events. `push_note_event()` fans shared-feed notes out to all users. `/api/stream` in app.py drains the queue with a 30s heartbeat.
- `reminders.py` — APScheduler `BackgroundScheduler`: reminder dispatch every 60s, calendar sync every 10min. Started only under `if __name__ == '__main__'` in app.py.
- `sms.py` — Twilio webhook command parser (`GET`/`FIND`/`LIST`/`REMIND ME`/free text), reply sending, MMS download. `REMIND ME` time parsing uses `dateparser.search.search_dates`.
- `voice.py`, `email_inbound.py`, `attachments.py`, `calendar_sync.py` — one module per inbound channel/integration.

**Key invariants:**

- **Never crash on missing config.** Every integration (Twilio, OpenAI, Mailgun, CalDAV) checks its own env vars and silently disables itself. Heavy SDK imports (`twilio`, `openai`, `caldav`) are deferred inside functions so the app starts without them being usable.
- **The DB row and the `.md` file are written together.** Any code path that creates or mutates a note must call `files.write_note_file()` and push an SSE event — this includes webhook paths, not just web routes. Changing a note's feed moves its file between folders.
- **Webhook routes (`/webhooks/*`) bypass session auth** and must verify provider signatures instead (Twilio `X-Twilio-Signature`, Mailgun HMAC). Everything else is guarded by the `before_request` session check; `PUBLIC_PATHS` in app.py is the allowlist.
- **Tags are global, uppercase, deduplicated**, with user-assigned hex colors (`DEFAULT_PALETTE` in database.py, assigned round-robin for auto-created tags). A note's first tag drives its card's left-border color.
- **Calendar sync never writes user content to CalDAV.** Attached notes/tags live only in SQLite and the `.md` stub; stub frontmatter is regenerated each sync while content below the `NOTES_MARKER` comment is preserved. Events deleted in Apple Calendar are marked orphaned, never removed.
- Visibility rule used everywhere: a user sees their own `feed='private'` rows plus anyone's `feed='shared'` rows.

## Frontend Note

The current `templates/` + `static/` UI is intentionally minimal — the real design is being produced separately (in Claude design) and will replace it. Don't invest in polishing the existing UI; keep `app.js`'s API usage as the reference for how the frontend consumes the backend.

## iOS App (`ios/`)

SwiftUI companion app (quick capture, voice→Whisper, share extension, send-anywhere sheet, reminder local notifications) implementing the Claude Design handoff. **It cannot be built in this environment** (no Xcode/iOS SDK) — the Xcode project is generated on the Mac with `cd ios && xcodegen`; see `ios/README.md`. The brand palette/type live in `ios/Shared/Theme.swift`; bundle/group identifiers in `ios/Shared/AppGroup.swift` must stay in sync with `ios/project.yml`. Mobile clients authenticate with bearer tokens (`POST /api/auth/token`), accepted by `require_login` in app.py; notes created from the app use `source: 'ios'`.
