# Remndrs roadmap

Living plan of what's shipped and what's next, so it lives in the repo instead
of in chat history. Update it as items land.

## Phase 1 — Reminders ✅ (complete)

- [x] Dismissed-banner persistence fix (#35)
- [x] Snooze (#37)
- [x] Recurring reminders (RRULE) (#38)
- [x] Web Push + PWA shell (#39)
- [x] Daily digest (email/SMS summary) (#40)

## Phase 2 — Notes power features ✅ (complete)

- [x] Note templates (#41)
- [x] Saved searches (#42)
- [x] Bulk multi-select (#42)
- [x] Attachment management UI (#42)
- [x] Wikilinks — `[[text]]` navigation (#42)
- [x] Per-todo due dates (#43)
- [x] Collapse ("Show more") + hide contents (#55)
- [x] Backlinks — "linked from" for `[[wikilinks]]` (#56)
- [x] Sub-task nesting — indented checklists (#56)

## Phase 3 — in progress

### Organization
- [x] Advanced search operators — `tag:`, `is:todo|note|pinned|hidden`,
      `has:attachment|reminder|due`, `due:today|overdue|week` (#60)
- [ ] Pinned saved-searches sidebar
- [x] Per-note colors (#61)

### Capture & AI
- [x] AI tag suggestions in the composer (OpenAI, self-disabling) (#62)
- [x] Summarize long notes — ✨ adds a TL;DR blockquote (#64)
- [x] Smarter voice/email parsing — AI transcript cleanup (regex fallback) +
      forwarded-email quote/signature trimming (#65)

### Organization
- [x] Pin saved searches as favorites — pinned ones lead the pill bar (#63)
      (chosen over a full sidebar, which would duplicate the existing pills)

## Notes / conventions

- Web + iOS stay in feature parity for note fields, feed views, and card
  actions (see CLAUDE.md). Pure web presentation (CSS, markdown/wikilink
  rendering) is exempt.
- Each item ships as its own PR off a current `main`; avoid stacking PRs that
  touch the same hot files (it caused merge breakage earlier in the project).
