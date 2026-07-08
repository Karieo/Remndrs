# PLAN: Backend integrity batch — authorization, invariant, and durability fixes

**Rank: 2 of 5.** A code audit found six real defects in the live server plus a
handful of one-line hardening gaps. Each fix is small and independent; together
they close every known correctness hole in the backend. Do them in the order
below (each step is separately testable; commit after each).

## Goal

No user can destroy or hijack another user's data; every note-mutating path
upholds the CLAUDE.md invariant (DB row + `.md` file + SSE together); a crash
can no longer destroy `.env`; SQLite connections are closed and lock-resistant.

## Files to touch

`app.py`, `database.py`, `telegram.py`, `digest.py`, `CLAUDE.md`, plus new tests
in `tests/` (suite exists and passes: `python3 -m pytest` → 274 passed; follow
the fixtures in `tests/conftest.py`).

## Steps, in order

### Step 1 — Owner-only destructive note operations (authorization)

`app.py:390-426`: both `PATCH /api/notes/<id>` and `DELETE /api/notes/<id>` gate
on `_can_see()` (`app.py:311-312`), which is `owner OR feed=='shared'`. So any
user can delete another user's shared note, or PATCH `feed='private'` on it —
which yanks it out of the owner's shared feed AND out of the editor's own view.
The MCP surface already requires ownership (`mcp_server.py:286`, `:339`), so the
two surfaces disagree.

Fix policy (keeps shared notes collaboratively editable, which the product
wants, but stops destruction):
- `DELETE`: require `note['user_id'] == session['user_id']`; otherwise 404.
- `PATCH`: allow content/tags/todos/color/pinned/hidden edits for anyone who
  `_can_see`, but if `data` contains `feed` or `archived` and the caller is not
  the owner, return 403 `{'error': 'Only the owner can move or archive this note'}`.
- Leave replies/shares as-is.

Add tests in `tests/test_visibility.py`: second user cannot DELETE, cannot PATCH
`feed`, CAN toggle a todo, on a shared note owned by user one.

### Step 2 — Calendar-note routes uphold the file+SSE invariant

`app.py:1279-1287` (`PATCH /api/calendar/notes/<id>`) and `app.py:1290-1296`
(`DELETE`) mutate only the DB — the `.md` event stub keeps stale/deleted text
and no SSE event fires (other open tabs never update). The create route
(`app.py:1259-1271`) writes the stub but pushes no SSE either.

Fix: factor a small helper next to these routes that, given the event, does:

```python
event = db.get_calendar_event(existing['event_id'])
owner = db.get_user(event['user_id'])
files.write_event_stub(event, owner['name'],
                       existing_filename=_event_stub_name(event, owner),
                       extra_content=updated_content_or_None)
sse.push_event(session['user_id'], 'calendar_event_updated',
               {'event_id': event['id']})
```

Call it from create/update/delete. Look at `calendar_sync.py` (~line 159) for
the SSE event name/shape it already uses and match it exactly — the frontend
listens for that name. For delete, pass the remaining notes' content (check how
`write_event_stub` composes `extra_content`; if it only takes one string, fetch
remaining notes for the event and join, or pass `None` when none remain).

Also (same routes): `POST /api/calendar/notes` (`app.py:1259-1266`) fetches the
event with **no visibility check** — any user can attach a note to anyone's
private event. Copy the visibility test used by `api_calendar_event`
(`app.py:1246-1247`) before creating.

### Step 3 — Contact-field hijack + 500 on email collision

`PATCH /api/users/me` (`app.py:664-671` → `database.py:375-388`) lets any member
set their own `twilio_number` / `telegram_chat_id` / `email` to arbitrary values.
Inbound SMS/Telegram/email route purely by these fields (`database.py:350,356,363`),
so a member can claim the owner's number and intercept their captures. Also
`users.email` is UNIQUE (`database.py:29`) and the update is unwrapped, so a
duplicate email raises `sqlite3.IntegrityError` → 500.

Fix in the route:
- Before applying, for each of the three fields being changed, check no OTHER
  user already has that value (`db.get_user_by_twilio_number` /
  `get_user_by_telegram_chat_id` / `get_user_by_email`, comparing ids); on
  conflict return 409 `{'error': '<field> is already linked to another user'}`.
- Wrap the DB call in `try/except sqlite3.IntegrityError` → 400, as a backstop.

### Step 4 — Attachments on shared notes saved under the wrong user

`POST /api/attachments` (`app.py:1158-1174`) saves bytes under the **uploader's**
folder (`attachments.py:44-46` uses the passed `user`), but download
(`app.py:1151-1152`) and delete (`app.py:1195-1196`) resolve under the **note
owner's** folder. A share-recipient's upload is written but never readable.

Fix: in `api_upload_attachment`, pass the note owner instead of the caller:

```python
owner = db.get_user(note['user_id'])
saved = attachments_module.save(upload.read(), upload.filename,
                                note_id, owner, mime_type=upload.mimetype)
```

Test (extend `tests/test_attachments.py`): user B uploads to user A's shared
note; GET of the returned filename succeeds as both A and B.

### Step 5 — Atomic `.env` writes

`_write_env` (`app.py:450-467`) opens `ENV_PATH` with `'w'` (truncate-then-write);
a crash mid-write destroys every secret (SESSION_SECRET, ENCRYPTION_KEY, all API
keys — and ENCRYPTION_KEY loss makes stored CalDAV credentials unrecoverable).

Fix: write to `ENV_PATH + '.tmp'` in the same directory, `f.flush()` +
`os.fsync(f.fileno())`, then `os.replace(tmp, ENV_PATH)`. Keep the
line-preserving merge logic as-is. Add a module-level `threading.Lock()` around
the read-merge-write so two concurrent settings PATCHes can't interleave.

### Step 6 — Close SQLite connections; enable WAL + busy_timeout

`database.py:268-273`: `with connect() as conn` commits but **never closes** —
sqlite3's context manager is transaction-scoped, not connection-scoped — so every
query leaks a connection until GC. And with APScheduler writing every 60s plus
web + SSE threads, default journal mode can throw `database is locked`.

Fix inside `connect()`:

```python
conn = sqlite3.connect(DB_PATH, timeout=5)
conn.row_factory = sqlite3.Row
conn.execute('PRAGMA foreign_keys = ON')
conn.execute('PRAGMA journal_mode = WAL')
conn.execute('PRAGMA busy_timeout = 5000')
```

Then make callers close. Do NOT hand-edit ~80 call sites: add

```python
@contextlib.contextmanager
def connect():
    conn = _open()          # the code above
    try:
        with conn:          # preserves commit/rollback semantics
            yield conn
    finally:
        conn.close()
```

…renaming the current function to `_open()`. Check first for any call site that
uses `connect()` WITHOUT a `with` block (grep `= connect()` and `connect().`) —
convert those to `with` form. `init_db()` uses `with connect()` already.

### Step 7 — One-line hardening trio

- `telegram.py:61`: replace `==` with `hmac.compare_digest(header_value, expected)`
  (import `hmac`; both args must be str — they are).
- `digest.py:77-83`: wrap the per-user body of `send_digests_for_hour`'s loop in
  `try/except Exception: log.exception(...)` so one user's failure doesn't skip
  the rest (mirror `reminders.py:121-127`).
- `app.py:336` `_auto_reminder_from_note`: `db.note_reminders(note['id'])`
  filters to unfired rows (`database.py:~932`), so editing a `#reminder` note
  after its reminder fired schedules a duplicate. Check `note_reminders`'s
  signature; add/use an `include_fired=True` form for this dedupe check only.

### Step 8 — Update stale docs (CLAUDE.md)

Two claims in CLAUDE.md are now false and will mislead future agents:
- "There is no test suite or linter configured" → there is `tests/` + `pytest.ini`
  (274 tests). Replace with the actual command: `pip install -r requirements-dev.txt && python3 -m pytest`.
- "Full-text search works through `notes_fts` + triggers; note content only, not
  todo items" → in reality nothing ever queries `notes_fts` (grep MATCH — zero
  hits); search is LIKE-based via `_apply_search` (`database.py:682-750`) and it
  DOES match todo text. Rewrite the sentence accordingly. (Removing the dead
  `notes_fts` table + triggers, `database.py:245-260`, is optional follow-up —
  if you do it, drop them in `_migrate()` with `DROP TRIGGER IF EXISTS` /
  `DROP TABLE IF EXISTS` so existing DBs migrate.)

## Edge cases a weaker model would miss

- Step 1: don't block non-owners from PATCHing `todos` — shared checklists are a
  core flow (household grocery list). Only `feed`/`archived`/DELETE are owner-only.
- Step 2: the SSE event name must match what `static/js/app.js` already listens
  for from `calendar_sync.py` — grep the frontend before inventing a new name.
- Step 4: the caller keeps permission to upload (`_can_see`); only the storage
  folder changes. Don't switch the permission check to owner-only.
- Step 6: sqlite3's `with conn` commits on success — keep that behavior inside
  the new context manager (`with conn:` inside, `close()` in `finally`), or
  every write in the app silently stops committing.
- Step 6: `PRAGMA journal_mode = WAL` returns a row; executing it inside an open
  transaction fails — run it right after connect, before any explicit BEGIN.
- Step 5: `os.replace` must target a temp file **on the same filesystem**
  (same directory), or it degrades to copy+delete and loses atomicity.
- Tests must not touch the real `.env`: `_write_env` tests should monkeypatch
  `app.ENV_PATH` to a tmp path (see how `tests/conftest.py` isolates NOTES_FOLDER
  and the DB, and follow that pattern).

## Acceptance criteria

- `python3 -m pytest` passes (274 existing + new tests; nothing skipped).
- New tests exist and fail on the pre-fix code for: shared-note DELETE by
  non-owner (Step 1), calendar-note PATCH regenerating the stub file on disk
  (Step 2), duplicate email → 4xx not 500 (Step 3), shared-note attachment
  readable after non-owner upload (Step 4).
- `python3 - <<'EOF'` proof for Step 6: open the app DB, run
  `PRAGMA journal_mode;` → returns `wal` after first app start.
- Kill-test for Step 5 documented in the PR: temp file exists momentarily,
  `.env` is never zero-length between writes (can be shown with a loop of
  PATCH /api/settings against a throwaway env).
- CLAUDE.md no longer claims there is no test suite and no longer claims search
  uses FTS.
