# PLAN: Fix iOS todo write paths that silently destroy due dates and sub-task nesting

**Rank: 1 of 5 — do this first.** This is not a missing feature, it is active data
corruption in the most common phone gesture. Per-todo due dates (`due_at`) and
sub-task indent (`indent`) shipped on web and in the iOS *read/display* side, but
every iOS *write* path rebuilds todos as `{text, checked}` only. The server's
`replace_todos()` (`database.py:623-634`) deletes all rows and re-inserts from the
payload, so any field the client omits becomes NULL/0. Result: checking off a
checkbox on the phone wipes due dates and nesting that were set on web. This
violates the CLAUDE.md parity invariant ("any change to note fields must land in
both clients").

## Goal

Every iOS write path round-trips `due_at` and `indent` for todo items, and the
iOS composer can read AND write the same todo syntax the web composer uses
(2-space indent for nesting, trailing `@YYYY-MM-DD` or `@YYYY-MM-DD HH:MM` for
due dates), so editing a todo note on the phone no longer loses data.

## Files to touch

1. `ios/Shared/Models.swift` — add a JSON-serialization helper on `TodoItem`
   (the struct is at ~line 95; it already decodes `due_at` as `dueAt: String?`
   and `indent: Int?`).
2. `ios/Shared/APIClient.swift` — `createNote(...)` (~line 68-79) currently maps
   `["text": $0.text, "checked": $0.checked]`.
3. `ios/Remndrs/Views/FeedView.swift` — `toggle(_ todo:in:)` (~line 253-260)
   rebuilds the whole todos array with only text/checked.
4. `ios/Remndrs/Views/ComposerView.swift` — two spots:
   - the `.onAppear` prefill for `editingNote` (~line 41-56) renders todos as
     `"[x] text"` only, dropping indent and due dates before the user even edits;
   - `save()` (~line 218-258) trims leading whitespace off every line and builds
     `TodoItem(id: nil, text:, checked:)`, then serializes `["text","checked"]`
     (~line 250).

Reference implementations to mirror (do NOT change these, just copy behavior):
- Web parser: `static/js/app.js:1670-1688` — indent = `min(4, floor(leadingSpaces/2))`
  (tabs count as 2 spaces), `[x]`/`[ ]` prefix for checked state, trailing
  `\s@(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?)\s*$` for due date (a space in the
  timestamp is normalized to `T`).
- Web checkbox toggle: `static/js/app.js:859` preserves `due_at` and `indent`.
- Server clamp: `database.py:634` clamps indent to 0-4 and coerces falsy `due_at`
  to NULL, so sending `indent: 0` or omitting keys is safe.

## Steps, in order

### Step 1 — serialization helper (Models.swift)

Add next to `TodoItem`:

```swift
extension TodoItem {
    /// JSON payload shape the server's replace_todos() expects. Always include
    /// every field the server stores — omitting one erases it (delete+reinsert).
    var jsonPayload: [String: Any] {
        var d: [String: Any] = ["text": text, "checked": checked]
        if let dueAt, !dueAt.isEmpty { d["due_at"] = dueAt }
        if let indent, indent > 0 { d["indent"] = indent }
        return d
    }
}
```

### Step 2 — APIClient.createNote

Replace the mapping in `createNote` with:

```swift
body["todos"] = todos.map { $0.jsonPayload }
```

### Step 3 — FeedView.toggle

Replace the body of `toggle(_ todo:in:)`'s map with:

```swift
let updated = note.todos.map { item -> [String: Any] in
    var d = item.jsonPayload
    if item == todo { d["checked"] = !item.checked }
    return d
}
```

(`item == todo` is fine: `TodoItem` is `Hashable` and both values come from the
same decoded note.)

### Step 4 — ComposerView prefill (round-trip render)

In `.onAppear`, render each todo with indent + checkbox + due suffix so the
parser in Step 5 can read it back losslessly:

```swift
lines += note.todos.map { item in
    let pad = String(repeating: "  ", count: item.indent ?? 0)
    let box = item.checked ? "[x] " : ""
    let due = (item.dueAt?.isEmpty == false)
        ? " @" + item.dueAt!.replacingOccurrences(of: "T", with: " ")
        : ""
    return pad + box + item.text + due
}
```

### Step 5 — ComposerView.save() parser

Rewrite the todo-lines block to mirror `app.js:1670-1688` exactly:

1. Split `body` on `\n`, **filter empty after trimming but keep the original
   line** (do not pre-trim the array — leading spaces carry the indent).
2. First non-empty line (trimmed) is `content`; the rest become todos.
3. Per line: count leading whitespace with tabs expanded to 2 spaces,
   `indent = min(4, lead/2)`; then trim; then match optional `^\[( |x|X)\]\s*`;
   then match trailing `\s@(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?)\s*$`, strip it
   from the text, and store it with the space replaced by `T`.
4. Build `TodoItem(id: nil, text: text, checked: checked, dueAt: dueAt, indent: indent)`.
5. In the PATCH/create payload use `todos.map { $0.jsonPayload }` (both the
   `fields["todos"]` edit branch and the `createNote` call).

### Step 6 — editor UX guard

`TextEditor` on iOS has smart-dash/autocorrect behavior; make sure the composer
text editor disables autocorrection-driven bracket/dash substitution if it isn't
already (check for `.autocorrectionDisabled` / `UITextInputTraits` on the
existing editor; only add if absent).

## Edge cases a weaker model would miss

- **Omitting a key deletes the data.** `replace_todos` is delete-and-reinsert.
  The fix is not "add due_at when the user sets one" — it is "always send back
  whatever the item already carries." That's why the helper lives on `TodoItem`
  and every path uses it.
- **`JSONSerialization` cannot encode `nil`.** Never put `dueAt` into the dict as
  an Optional; either include a real String or omit the key (the helper handles
  this). Do not use `NSNull()` here — the server treats missing and null the
  same for todos, and mixed `Any?` maps crash `JSONSerialization`.
- **Do not trim before measuring indent.** The current code maps
  `trimmingCharacters(in: .whitespaces)` over lines *first*; that must move to
  after the indent count.
- **Tabs**: web expands each tab to 2 spaces before counting. Match it.
- **Due timestamps are naive local** (`2026-07-10T14:00`, no `Z`, no offset).
  Never run them through `ISO8601DateFormatter` for output; store and resend the
  string verbatim. Display parsing already exists (`RemndrsDate.parse`).
- **Prefill/parse symmetry**: a todo whose *text itself* ends in something like
  `@2026-01-01` would gain a due date on re-save. Acceptable (web has the same
  behavior), but do not "fix" it asymmetrically on one side only.
- **`TodoItem(id: nil, text:, checked:)` still compiles** after the struct gains
  use of `dueAt`/`indent` because optional `var` members get `nil` defaults in
  the memberwise init — but the new parser should pass them explicitly anyway.
- **The share extension** (`ios/RemndrsShare/`) creates plain notes, not todos —
  no changes needed there, but it links `Models.swift`/`APIClient.swift`, so keep
  the helper in the `Shared` group or the extension target breaks.

## Acceptance criteria

The iOS app cannot be built in this environment (no Xcode), so verify in two layers:

1. **Server-side round-trip proof** (runnable here): start the app with throwaway
   env (see CLAUDE.md smoke test), create a todo note via curl with
   `"todos": [{"text":"a","checked":false,"due_at":"2026-07-10T14:00","indent":1}]`,
   then PATCH it with the exact JSON your new Swift code would produce for a
   checkbox toggle (same fields, `checked` flipped), then GET the note and assert
   `due_at` and `indent` survived. This documents the contract the Swift code
   must satisfy — paste the three curl commands and their output into the PR.
2. **Code-level checklist** (review, since no simulator): every call site that
   sends `todos` uses `jsonPayload` (grep `"todos"` under `ios/` — there must be
   no remaining `["text": $0.text, "checked": $0.checked]` literal); the composer
   prefill emits indent/checkbox/due and `save()` parses all three; no `Optional`
   values are placed in a `[String: Any]`.
3. On-Mac manual test (document in PR for the human): create a nested, due-dated
   todo list on web → toggle one item in the iOS app → reload web → dates and
   nesting intact; edit the note in the iOS composer, add a line `  child @2026-12-01`,
   save → web shows it nested with a due badge.
