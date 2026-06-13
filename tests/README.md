# Tests

Pytest suite covering the highest-risk logic in Remndrs. No external services
are touched — every integration reads its credentials with `os.getenv` at call
time, so `conftest.py` strips real secrets and points the DB / notes folder at a
throwaway temp dir before importing the app.

## Running

```bash
pip install -r requirements-dev.txt
pytest                       # run everything
pytest --cov=. --cov-report=term-missing   # with coverage
pytest tests/test_auth.py    # one file
```

## Layout

| File | Area | Tier |
|------|------|------|
| `test_auth.py` | `require_login`, `PUBLIC_PATHS` allowlist, session + bearer auth, login throttle | 1 (security) |
| `test_visibility.py` | `list_notes` private/shared rule, `_can_see`, owner-scoped retrieval | 1 (security) |
| `test_webhook_signatures.py` | Mailgun HMAC, Telegram secret, Twilio unconfigured-rejects | 1 (security) |
| `test_parsers.py` | SMS / Telegram command grammar, hashtags, `_fmt_date`/`_snippet` | 2 (parsing) |
| `test_files.py` | title sanitizing, frontmatter, filename collisions, calendar stub marker preservation | 2 (parsing) |
| `test_email_parsing.py` | HTML strip, tag-line / subject-prefix extraction, reminder detection | 2 (parsing) |
| `test_voice.py` | transcript cleanup, spoken tag extraction | 2 (parsing) |
| `test_attachments.py` | extension parsing, allow-list gate, markdown links, traversal-safe resolve | 2 (parsing) |
| `test_reminders.py` | natural-language `parse_remind_text` contract | 2 (parsing) |
| `test_mcp.py` | JSON-RPC dispatch (initialize/ping/tools/batch/errors), tool handlers | 2 (parsing) |

## Fixtures (`conftest.py`)

- `reset_db` (autouse) — empties every base table before each test.
- `make_user` / `make_note` — factories for seeding rows.
- `client` — Flask test client (imports `app` lazily).

## Not yet covered

Calendar CalDAV sync (`calendar_sync.py`), SSE fan-out, and the bulk of
`app.py`'s route bodies (send-anywhere, share/replies, settings). These are the
natural next slice (Tier 3 — stateful integration paths).
