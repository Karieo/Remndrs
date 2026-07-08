# PLAN: MCP server — today_agenda, delete_note, note-linked reminders, add_todo_items

**Rank: 5 of 5.** The MCP surface (`mcp_server.py`, 13 tools) is already rich —
notes CRUD-ish, reminders, tags, attachments — but four gaps block the most
natural Claude conversations: "what's on today?" (no calendar/agenda access at
all), "delete that note" (reminders are deletable, notes aren't), "remind me
about this note" (`add_reminder` can't link a `note_id`), and "add milk to the
grocery list" (`complete_todo` toggles but nothing appends). All four are
mechanical: the DB layer already has every function needed.

## How tool registration works (read first)

Adding a tool is a three-edit, append-only change in `mcp_server.py`:
1. Implement `_tool_<name>(user, args)` → returns a plain string; raise
   `ToolError` (`mcp_server.py:48`) for user-correctable failures.
2. Append a schema dict to `TOOLS` (`mcp_server.py:469-682`).
3. Append `'<name>': _tool_<name>` to `TOOL_HANDLERS` (`mcp_server.py:684-698`).
Dispatch and `tools/list` pick it up automatically. Also extend the
`INSTRUCTIONS` string (`mcp_server.py:30-43`) so Claude discovers the new verbs.
Reuse existing helpers: `_parse_when` (:55), `_limit` (:434), `_format_notes`
(:424), `_human_time`, and the ownership pattern
`if note['user_id'] != user['id']: raise ToolError(...)` (e.g. :286).

## Files to touch

1. `mcp_server.py` — four handlers + schemas + handler-map entries + INSTRUCTIONS.
2. `tests/test_mcp.py` — one test per tool (198 lines of existing patterns to copy).
3. `CLAUDE.md` — the `mcp_server.py` bullet lists only 5 tools; it's stale.
   Update it to say "tool registry (see TOOLS in mcp_server.py)" rather than
   enumerating.

No app.py changes: the `/mcp` route just dispatches.

## Steps, in order

### Step 1 — `delete_note`

Handler: fetch `db.get_note(note_id)`; ToolError if missing; require
`note['user_id'] == user['id']` (owner-only — stricter than web on purpose,
matching the existing MCP update_note stance). Then replicate the web delete
path **exactly** (`app.py:416-426`), because of the CLAUDE.md invariant (DB row,
`.md` file, SSE together):

```python
owner = db.get_user(note['user_id'])
files.delete_note_file(note, owner['name'])
db.delete_note(note_id)
sse.push_note_event('note_deleted', {'id': note_id, 'feed': note['feed'],
                                     'user_id': note['user_id']})
```

`files` and `sse` may not be imported in mcp_server.py yet — check the imports
at the top and add them (both are import-safe, no config needed).
Return `f'Deleted note "{<first line, truncated>}" (id: {note_id}).'`
Schema: `note_id` required. Description must tell Claude this is permanent and
to confirm with the user for anything non-trivial.

### Step 2 — `today_agenda`

No arguments (optional `date` string, default today). Compose three sections
into one string:

1. **Reminders today** — `db.list_reminders(user['id'])` (`database.py:924`)
   filtered to `fire_at` between `date`T00:00:00 and T23:59:59 (string compare
   works: naive local ISO sorts lexicographically). Note whether each repeats.
2. **Calendar events today** — `db.list_calendar_events(user['id'], start, end)`
   (`database.py:1155`). Read that function first for exact parameter semantics
   (ISO strings) and the row shape (title/start/end/calendar/feed keys). Respect
   visibility: it's already scoped by user_id — verify whether it includes
   shared-feed events of others; mirror whatever `GET /api/calendar/events`
   (`app.py`, grep `api_calendar_events`) does so MCP shows the same agenda the
   web calendar rail shows.
3. **Todos due today/overdue** — `digest.py` already builds exactly this for the
   daily digest; read `digest.build_digest` (`digest.py`) and reuse its query
   (likely a db helper — grep how it finds due todos) rather than writing a new
   one.

Empty agenda → return a friendly "Nothing scheduled for {date}." (never an error).
Format times with the existing `_human_time` helper.

### Step 3 — `note_id` on `add_reminder`

`_tool_add_reminder` (`mcp_server.py:157-179`) already calls
`db.create_reminder(...)`, which accepts `note_id` (`database.py:904`). Add an
optional `note_id` arg: when present, fetch the note, ToolError if missing or
not visible (owner OR `feed == 'shared'` — reminders on shared notes are fine
since the reminder row itself is owned by the caller). Pass it through. Append
"about note (id: …)" to the return string. Add `note_id` to the tool schema as
optional.

### Step 4 — `add_todo_items`

Args: `note_id` (required), `items` (required, array of strings). Handler:
- Fetch note; visibility: owner OR shared (shared checklists are the household
  flow — match web PATCH semantics, not owner-only).
- Get current todos from the note dict (`db.note_to_dict` output has `todos`
  with `text/checked/due_at/indent` — verify by reading `note_to_dict`,
  `database.py:556-576`).
- Append the new items as `{'text': t, 'checked': False}` and call
  `db.replace_todos(note_id, existing + new)` — **the existing dicts must keep
  their `due_at` and `indent` keys**, since replace_todos deletes and re-inserts
  everything (`database.py:623-634`).
- If the note's `type` isn't `'todo'`, also `db.update_note(note_id, type='todo')`
  so the items render as a checklist (verify web behaves this way — grep how
  app.js decides to render checkboxes; if type doesn't matter for rendering,
  skip this).
- Then the invariant: `_persist` the file and push SSE. mcp_server almost
  certainly already does this for `update_note`/`complete_todo` — find that code
  (near `mcp_server.py:281-360`) and reuse the exact same post-mutation calls.
- Return "Added N item(s) to …" with the new list rendered as checkboxes.

### Step 5 — INSTRUCTIONS + docs

Weave the four new verbs into `INSTRUCTIONS` (keep it one paragraph, same voice):
agenda for "what's on today", delete_note (permanent), add_reminder's note_id,
add_todo_items for appending to checklists. Update the CLAUDE.md mcp_server
bullet.

### Step 6 — tests (`tests/test_mcp.py`)

Copy the existing call pattern (the file shows how to fake a token/user and post
JSON-RPC `tools/call`). Add:
- delete_note: create note → delete → note gone from DB AND `.md` file gone from
  the notes folder (conftest gives a tmp NOTES_FOLDER); deleting another user's
  note → isError.
- today_agenda: seed one reminder today + one tomorrow → only today's in output;
  empty case returns the friendly string.
- add_reminder with note_id → reminder row has note_id.
- add_todo_items: note with an existing todo carrying due_at + indent → append
  one → old item still has due_at/indent (regression-proof the replace_todos
  trap); non-visible note → isError.

## Edge cases a weaker model would miss

- **`replace_todos` erases what you don't resend** — appending todos must pass
  the FULL existing list including `due_at`/`indent`, not just texts.
- **delete_note must delete the `.md` file and push SSE** — a DB-only delete
  leaves an orphan file in iCloud/Obsidian and stale cards on open tabs
  (CLAUDE.md invariant #2). Same for add_todo_items: file + SSE after mutation.
- **Naive local times, lexicographic filtering** — don't introduce `datetime`
  timezone handling; the whole codebase compares naive ISO strings.
- **tools/list output is user-facing API** — schema `description` fields are what
  Claude reads; write them for the model (state defaults, formats, and that ids
  come from search results' `(id: …)` suffix, matching existing descriptions).
- **Don't rename or reorder existing tools** — claude.ai connectors cache tool
  lists; append only.
- **`digest.build_digest` may bundle formatting with querying** — reuse its DB
  query, not its output string; the agenda has its own format.
- MCP notes must keep `source='claude'` behavior for add paths — untouched here,
  but don't copy add_note code into add_todo_items and accidentally change source.

## Acceptance criteria

- `python3 -m pytest tests/test_mcp.py` passes with the new tests; full suite
  stays green.
- `curl` proof against a throwaway server (see CLAUDE.md smoke test; mint a
  token via `POST /api/settings/claude/connect` as owner, then JSON-RPC to
  `/mcp/<token>`): `tools/list` shows 17 tools; `today_agenda` returns seeded
  reminder + event; `delete_note` removes the `.md` from disk (`ls` the notes
  folder before/after). Paste transcript in the PR.
- Grep proof: every new mutating handler calls both a `files.` write/delete and
  an `sse.push` in the same code path.
