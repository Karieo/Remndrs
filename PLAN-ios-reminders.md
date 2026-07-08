# PLAN: iOS reminder management — create, list, snooze, dismiss, delete on the phone

**Rank: 3 of 5.** The app is named Remndrs and the phone is where reminders get
set, yet iOS is read-only: `ReminderSyncer.swift` mirrors existing server
reminders into local notifications, but there is no way to create, snooze,
dismiss, or delete one from the app. Web has all of it. This is the largest
remaining feature-parity gap (CLAUDE.md invariant), and every server endpoint
already exists — this is purely client work.

## Server API contract (already live — do not change the server)

All under bearer-token auth, which `APIClient.send` already handles:

- `GET /api/reminders` (`app.py:900-902`) → array of reminder objects.
- `GET /api/reminders/pending` (`app.py:905-908`) → fired-but-unacknowledged.
- `POST /api/reminders` (`app.py:911-923`) — body:
  `{"message": str, "fire_at": "YYYY-MM-DDTHH:MM:SS", "note_id": str?, "recurrence": str?, "notify_sms": bool?, "notify_web": bool?}`.
  `fire_at` is **naive local ISO — no timezone suffix, no Z** (server wall
  clock). `recurrence` accepts natural keywords ("daily", "weekly", "monthly",
  "yearly", "weekdays", "every monday") or a raw RRULE — normalized server-side
  by `reminders.normalize_recurrence` (`reminders.py:80-96`); unrecognized values
  silently become one-shot, so only offer the known keywords. Returns 201 + the
  reminder JSON.
- `POST /api/reminders/<id>/snooze` (`app.py:952-966`) — body `{"minutes": int}`
  or `{"preset": "1h"|"tonight"|"tomorrow"}`. Returns the updated reminder.
- `POST /api/reminders/<id>/dismiss` (`app.py:969-975`) — empty body, `{"success": true}`.
- `DELETE /api/reminders/<id>` (`app.py:978-984`).

The `Reminder` model already exists in `ios/Shared/Models.swift` (~line 131,
decodes `id`, `message`, `fireAt`, recurrence — read it and add any missing
fields as optionals, e.g. `note_id`, `fired`, `acknowledged`, so older servers
still decode).

## Files to touch

1. `ios/Shared/APIClient.swift` — add five methods next to the existing
   `reminders()` (~line 128).
2. `ios/Shared/Models.swift` — extend `Reminder` with optional fields as needed.
3. `ios/Remndrs/Views/RemindersView.swift` — **new file**: the list sheet.
4. `ios/Remndrs/Views/FeedView.swift` — toolbar entry point (bell icon) to
   present RemindersView; badge with pending count.
5. `ios/Remndrs/Views/ComposerView.swift` — optional "Remind me" row (toggle +
   `DatePicker` + repeat `Picker`) that POSTs a reminder linked to the saved
   note.
6. `ios/Remndrs/ReminderSyncer.swift` — expose a `resync()` you can call after
   any create/snooze/delete so local notifications update immediately.
7. `ios/project.yml` — only if new files aren't picked up automatically; the
   project uses xcodegen with directory globs (check `sources:` — if the whole
   `Views` folder is globbed, no change needed).

## Steps, in order

### Step 1 — APIClient methods

```swift
func createReminder(message: String, fireAt: String, noteID: String? = nil,
                    recurrence: String? = nil) async throws -> Reminder
func pendingReminders() async throws -> [Reminder]
func snoozeReminder(id: String, minutes: Int? = nil, preset: String? = nil) async throws -> Reminder
func dismissReminder(id: String) async throws
func deleteReminder(id: String) async throws
```

Build bodies with `[String: Any]`, omitting nil keys (never insert Optionals).
Format `fireAt` with a fixed formatter:
`DateFormatter` with `dateFormat = "yyyy-MM-dd'T'HH:mm:ss"`, `locale = Locale(identifier: "en_US_POSIX")`,
and the **device's local time zone** (matches how RemndrsDate parses server times
— check `RemndrsDate` in Models.swift and reuse its formatter if one exists).

### Step 2 — RemindersView

A sheet listing upcoming reminders (`api.reminders()`) with a "Needs attention"
section on top for `pendingReminders()`. Rows show message, humanized fire time,
and a repeat glyph when `recurrence != nil`. Actions:
- swipe/context menu: Snooze (submenu: 15 min / 1 hour / Tonight / Tomorrow —
  map to `{"minutes":15}`, `{"preset":"1h"}`, `{"preset":"tonight"}`,
  `{"preset":"tomorrow"}`), Dismiss (pending only), Delete.
- After every action: reload the list and call `ReminderSyncer` resync.

Match the app's existing look: reuse `Theme.*` fonts/colors and the card idiom
from `NoteCardView.swift` (don't invent new styles — see `Theme.swift`).

### Step 3 — FeedView entry point

Add a bell `ToolbarItem` (or a button in the existing custom header — FeedView
has a hand-rolled header; put it where the settings gear lives) that presents
`RemindersView` as a sheet. Load `pendingReminders().count` alongside the
existing `refreshSharedCount()` call and show a small badge when > 0.

### Step 4 — Composer "Remind me"

Below the tag preview row in ComposerView: a toggle; when on, show a compact
`DatePicker` (`.dateAndTime`, default = next hour) and a repeat `Picker` with
options Never/Daily/Weekly/Monthly/Yearly/Weekdays (send lowercase keyword, or
omit for Never). In `save()`, after the note is created/updated successfully,
if the toggle is on call `createReminder(message: <first line of content>,
fireAt: <picked date>, noteID: note.id, recurrence: <keyword or nil>)`.

Mirror web's behavior guard: the server may have already auto-created a reminder
if the note carries the `#reminder` tag with a parseable time
(`_auto_reminder_from_note`, `app.py:330-347` — the returned note JSON then has
a `reminder` key). If the create/PATCH response includes `"reminder"`, skip the
manual POST to avoid doubles. This requires adding an optional
`reminder: AutoReminder?` (with `fire_at`, `message`) to `Note` in Models.swift —
optional so older servers decode.

### Step 5 — ReminderSyncer resync hook

Read `ReminderSyncer.swift`; it already fetches reminders and schedules
`UNUserNotificationCenter` requests. Expose its sync entry point (make it a
shared instance or a static func) and call it after create/snooze/dismiss/delete
so a reminder made on the phone notifies even if the server push path (SSE/web
push) never reaches iOS. Make sure re-syncing first removes previously scheduled
requests for ids that no longer exist (it likely already does — verify, and fix
if it only adds).

## Edge cases a weaker model would miss

- **Naive local time.** Do not use `ISO8601DateFormatter` (it appends offsets/Z);
  the server treats `fire_at` as its own wall clock. If phone and server time
  zones differ the reminder fires at server-local time — acceptable and matches
  web, but never send an offset, which the server would store verbatim and then
  compare against naive `datetime.now()` lexically.
- **Recurrence strings are normalized server-side but silently.** An arbitrary
  string (e.g. "every 2 weeks") becomes a ONE-SHOT reminder with no error. Only
  present the supported keywords.
- **Snooze body is exclusive**: send `minutes` OR `preset`, never both keys.
- **`dismiss` only makes sense for fired reminders**; hide it for upcoming rows.
- **Auto-reminder double-create** (Step 4's `reminder` key check).
- **Decode resilience**: every new `Reminder`/`Note` field must be optional with
  a CodingKeys entry (project convention, see the `dueAt` comment in Models.swift).
- **Don't touch the web client** — it already has all of this; this plan only
  brings iOS to parity. No server changes at all.

## Acceptance criteria

Cannot build iOS here (no Xcode); verify in layers:

1. **Contract proof via curl** (runnable here): against a throwaway server,
   create / list / snooze(preset tonight) / dismiss / delete a reminder using
   exactly the JSON bodies the new Swift methods produce; paste commands +
   responses in the PR.
2. **Code checklist**: five new APIClient methods; RemindersView added and
   reachable from FeedView; composer toggle POSTs with `note_id` and skips when
   the note response contains `reminder`; all new model fields optional;
   formatter is `yyyy-MM-dd'T'HH:mm:ss` with no time zone designator in output.
3. **On-Mac manual test** (document in PR): set a reminder for +2 minutes on the
   phone with repeat "daily" → it appears on web's reminders overlay; when it
   fires, banner appears on web and a local notification on the phone; snooze
   from the phone updates `fire_at` on web; a new occurrence exists after firing
   (recurrence row per `reminders.py:146-155`).
