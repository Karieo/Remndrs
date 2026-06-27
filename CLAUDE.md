# CLAUDE.md

## STATUS (updated 2026-06-27)
- Status: ~98% complete, stable. Waiting on new feature ideas before more work.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Remndrs is a local-first personal notes/reminders app that runs on the user's Mac. Notes arrive via web UI, SMS (Twilio), email (Mailgun), or voice calls (Twilio + Whisper), and every note is also written as an Obsidian-compatible `.md` file to an iCloud Drive folder. The full product spec lives in the original handoff document; the README covers integration setup.

## Commands

```bash
pip install -r requirements.txt   # deps (or ./setup.sh for the full Mac install: venv, secrets, launchd)
python3 app.py                    # run — http://localhost:3000 (falls back to 3001/3002)
```

On a Mac, `setup.sh` installs into `./venv` and points launchd at `venv/bin/python`; `install.sh` is the curl-able bootstrap and `uninstall.sh` reverses it (notes are never deleted).

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
- `sse.py` — per-connection `queue.Queue` subscriptions (`subscribe`/`unsubscribe`), so every open tab/device gets every event. `push_note_event()` fans shared-feed notes out to all users. `/api/stream` in app.py drains a subscription with a 30s heartbeat; it accepts bearer tokens, which is how the iOS app (`ios/Remndrs/SSEClient.swift`) connects.
- `reminders.py` — APScheduler `BackgroundScheduler`: reminder dispatch every 60s, calendar sync every 10min. Started only under `if __name__ == '__main__'` in app.py.
- `sms.py` — Twilio webhook command parser (`GET`/`FIND`/`LIST`/`REMIND ME`/free text), reply sending, MMS download. `REMIND ME` time parsing uses `dateparser.search.search_dates`.
- `telegram.py` — Telegram bot channel (no carrier registration, unlike SMS); reuses `sms.py`'s command helpers. The webhook self-registers via `POST /api/settings/telegram/connect` (calls Telegram `setWebhook` with a generated `TELEGRAM_WEBHOOK_SECRET`, which Telegram echoes in the `X-Telegram-Bot-Api-Secret-Token` header and `verify_secret` checks — that's this channel's signature equivalent). Users link by pasting the chat ID (`telegram_chat_id` on `users`) the bot replies with.
- `mcp_server.py` — remote MCP endpoint (`/mcp`) so Claude can capture and search notes: stateless JSON-RPC dispatch + tool registry (add_note/add_reminder/search_notes/recent_notes/get_notes_by_tag). app.py owns the route and resolves the user from either the capability-URL token (`/mcp/<token>`, for claude.ai custom connectors which can't send headers) or an `Authorization: Bearer` header (Claude Code) — both rows in `api_tokens`, minted/rotated via `POST /api/settings/claude/connect`. Notes get `source='claude'`.
- `voice.py`, `email_inbound.py`, `attachments.py`, `calendar_sync.py` — one module per inbound channel/integration.

**Key invariants:**

- **Never crash on missing config.** Every integration (Twilio, OpenAI, Mailgun, CalDAV) checks its own env vars and silently disables itself. Heavy SDK imports (`twilio`, `openai`, `caldav`) are deferred inside functions so the app starts without them being usable. Integration credentials are editable at runtime from ⚙ Settings (owner only): `PATCH /api/settings` writes `.env` AND `os.environ`, so env reads must stay lazy (`os.getenv` at call time, never cached at import).
- **The DB row and the `.md` file are written together.** Any code path that creates or mutates a note must call `files.write_note_file()` and push an SSE event — this includes webhook paths, not just web routes. Changing a note's feed moves its file between folders.
- **Webhook routes (`/webhooks/*`) bypass session auth** and must verify provider signatures instead (Twilio `X-Twilio-Signature`, Mailgun HMAC). Everything else is guarded by the `before_request` session check; `PUBLIC_PATHS` in app.py is the allowlist.
- **Tags are global, uppercase, deduplicated**, with user-assigned hex colors (`DEFAULT_PALETTE` in database.py, assigned round-robin for auto-created tags). A note's first tag drives its card's left-border color.
- **Calendar sync never writes user content to CalDAV.** Attached notes/tags live only in SQLite and the `.md` stub; stub frontmatter is regenerated each sync while content below the `NOTES_MARKER` comment is preserved. Events deleted in Apple Calendar are marked orphaned, never removed.
- Visibility rule used everywhere: a user sees their own `feed='private'` rows plus anyone's `feed='shared'` rows.
- **Web and iOS stay in feature parity.** Any change to note fields, feed views, or card actions must land in both clients in the same PR: the API/JSON shape (`ios/Shared/Models.swift` — new fields decode as optionals so the app survives older servers), the feed views (`ios/Remndrs/Views/FeedView.swift`), and the card context menu (`ios/Remndrs/Views/NoteCardView.swift`). Web-only presentation (CSS, markdown rendering) is exempt.

## Frontend Note

The `templates/` + `static/` UI implements the Claude Design handoff (warm editorial palette, Playfair/Lora/IBM Plex Mono via Google Fonts CDN, channel chips, dark/light themes). Design tokens are CSS custom properties at the top of `app.css` (`:root[data-theme=…]`); the channel color system (`CH` in app.js) must stay in sync with `Channel` in `ios/Shared/Theme.swift`. Notes' visual channel comes from `source` (`web`/`ios` → App); calendar events render as separate purple-spine cards. The card `···` menu drives send-anywhere (`/api/notes/:id/send`, `/to-event`) and person-to-person sharing (`/api/notes/:id/share` + `/replies`, backed by `note_shares`/`note_replies`; replies append to the `.md` under `## Replies`). Shared-card attribution prefers the note's `share` record over plain ownership.

## iOS App (`ios/`)

SwiftUI companion app (quick capture, voice→Whisper, share extension, send-anywhere sheet, reminder local notifications) implementing the Claude Design handoff. **It cannot be built in this environment** (no Xcode/iOS SDK) — the Xcode project is generated on the Mac with `cd ios && xcodegen`; see `ios/README.md`. The brand palette/type live in `ios/Shared/Theme.swift`; bundle/group identifiers in `ios/Shared/AppGroup.swift` must stay in sync with `ios/project.yml`. Mobile clients authenticate with bearer tokens (`POST /api/auth/token`), accepted by `require_login` in app.py; notes created from the app use `source: 'ios'`.
