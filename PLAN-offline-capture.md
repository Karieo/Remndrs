# PLAN: Offline capture — app-shell caching + queued note creation (PWA)

**Rank: 4 of 5.** Remndrs' whole point is friction-free capture, but the PWA is
a shell in name only: `static/sw.js` (31 lines) handles push + notification
clicks and nothing else — no `install`, no `fetch`, no caching. With no network
the installed app won't even open, and a note typed in a dead zone is lost.
This plan makes the app open offline and queue captures until connectivity
returns. Web-only mechanics (capture transport), so the iOS-parity invariant
does not apply; iOS has its own local queue semantics.

## Current state (verified anchors)

- `static/sw.js:4-31` — `push` + `notificationclick` only. Keep both untouched.
- SW is served at root scope with `Service-Worker-Allowed: /` and
  `Cache-Control: no-cache` (`app.py:1015-1021`) — updates propagate on reload;
  no version-busting URL needed.
- Registration: `initPush()` in `static/js/app.js:1261-1269` registers `/sw.js`
  **only when web push is configured** — offline caching must not depend on that.
- API helper: `api()` at `static/js/app.js:67-73` — all fetches funnel through it.
- Note creation: `saveNote()` at `static/js/app.js:1662-1706` POSTs `/api/notes`.
- Real-time: `/api/stream` is a long-lived SSE response — the SW fetch handler
  must never intercept it.
- Frontend loads marked.js/DOMPurify and Google Fonts from CDNs
  (`templates/index.html`) — cross-origin, and app.js already degrades to
  escaped plain text when DOMPurify is absent (comment at `app.js:77-79`).

## Files to touch

1. `static/sw.js` — add `install`, `activate`, `fetch`, and (optionally) `sync`
   handlers. Keep the existing push handlers verbatim.
2. `static/js/app.js` — unconditional SW registration; outbox (IndexedDB) +
   queue-on-failure in the note-create path; flush triggers; a "queued" UI hint.
3. `static/css/app.css` — one small style for the queued badge/banner.
4. `templates/index.html` — nothing required; only touch if adding the offline
   banner container.

No server changes: `POST /api/notes` (`app.py:372-387`) already accepts a
`source` field and the queued replay is an ordinary authenticated POST.

## Steps, in order

### Step 1 — app-shell cache in sw.js

```js
const CACHE = 'remndrs-shell-v1';   // bump the suffix on every sw.js change
const SHELL = ['/', '/static/js/app.js', '/static/css/app.css',
               '/static/favicon.svg', '/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});
```

### Step 2 — fetch strategy in sw.js

```js
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;                  // never touch POST/PATCH/DELETE
  if (url.origin !== location.origin) return;              // CDNs: browser default
  if (url.pathname.startsWith('/api/')) return;            // APIs + SSE stream: never intercept
  if (url.pathname.startsWith('/webhooks/') || url.pathname.startsWith('/mcp')) return;
  if (e.request.mode === 'navigate') {
    // network-first so login redirects and fresh HTML win; shell as fallback
    e.respondWith(fetch(e.request).catch(() => caches.match('/')));
    return;
  }
  // static assets: cache-first, refresh in background
  e.respondWith(caches.match(e.request).then(hit => {
    const refresh = fetch(e.request).then(res => {
      if (res.ok) caches.open(CACHE).then(c => c.put(e.request, res.clone()));
      return res;
    }).catch(() => hit);
    return hit || refresh;
  }));
});
```

### Step 3 — always register the SW (app.js)

`initPush()` currently registers `/sw.js` only when push keys are configured.
Add, in the app's init path (find where `initPush` is invoked), an unconditional
`navigator.serviceWorker.register('/sw.js')` guarded by
`if ('serviceWorker' in navigator)`. `initPush` can then reuse
`navigator.serviceWorker.ready` — make sure double registration is harmless
(it is; same script URL is a no-op) rather than refactoring initPush.

### Step 4 — IndexedDB outbox (app.js)

A tiny helper (no library):

```js
const OUTBOX_DB = 'remndrs-outbox', OUTBOX_STORE = 'notes';
function outboxDB(){ return new Promise((ok, err) => {
  const r = indexedDB.open(OUTBOX_DB, 1);
  r.onupgradeneeded = () => r.result.createObjectStore(OUTBOX_STORE, { keyPath: 'id', autoIncrement: true });
  r.onsuccess = () => ok(r.result); r.onerror = () => err(r.error);
});}
```

Plus `outboxAdd(body)`, `outboxAll()`, `outboxDelete(id)` using ordinary
transactions.

### Step 5 — queue on failure in saveNote()

In `saveNote()`'s catch (and only for the **create** path, not edits): if the
failure is a network failure (`err instanceof TypeError` — fetch rejects with
TypeError offline; HTTP errors from `api()` are `Error` with a message and must
NOT be queued), then `outboxAdd(body)`, close the composer, and show a toast/
banner "Saved offline — will sync" plus a persistent small indicator with the
queued count. Tag queued bodies with `source: 'web'` (already set) — do not
invent a new source value; `CH` in app.js and iOS `Channel` would both need it
(parity), so reuse `web`.

### Step 6 — flush triggers

`flushOutbox()`: read all rows, POST each via the existing `api('/api/notes', …)`,
delete each row only on success; stop the loop on the first network failure
(preserve order). Call it: on app init after login state is confirmed, on
`window.addEventListener('online', …)`, and on `visibilitychange` → visible.
Optionally also register Background Sync (`registration.sync.register('flush-notes')`
in Step 5's catch, with a `sync` handler in sw.js that posts a message to open
clients — but keep the client-side triggers as the primary mechanism since
Background Sync is Chromium-only and Safari/iOS never fires it).

### Step 7 — queued-count UI

Reuse the existing toast/notification pattern in app.js (grep for how errors are
surfaced today) — a pill near the composer button: "N queued". Update after every
enqueue/flush. One CSS class in app.css using existing design tokens.

## Edge cases a weaker model would miss

- **Never intercept `/api/stream`.** A cached/buffered SSE response bricks
  real-time updates for every tab. The `startsWith('/api/')` guard covers it —
  don't narrow that guard.
- **Only queue network failures.** A 400 (bad payload) or 401 (logged out)
  must surface, not silently loop in the outbox forever. During flush, a 401
  response means the session died: stop flushing, keep rows, let `api()`'s
  redirect to `/login` happen; rows flush after next login.
- **Don't queue edits/PATCHes.** Replaying stale edits after hours offline can
  clobber newer server state; scope is capture (create) only. `saveNote` handles
  both create and edit — branch on `editingNoteId`.
- **Attachments can't be queued** (multipart, large). If `composerAttachments`
  is non-empty when offline, still queue the text note but warn "attachments
  need a connection" and drop them from the queued body (`attachComposerFiles`
  runs post-create anyway — just skip it for queued notes).
- **`caches.put` on non-OK responses** poisons the cache — the `res.ok` check in
  Step 2 is load-bearing.
- **Navigation fallback must be network-first**, or users get a stale app after
  deploys and the login page becomes unreachable behind the cached shell.
- **Bump `CACHE` version** whenever SHELL contents change; the activate handler
  deletes old caches — without the bump, stale JS pairs with new HTML.
- **Cached `/` is the logged-in template** (`templates/index.html` is rendered
  per-user — it embeds `user`). Verify what `render_template('index.html', user=…)`
  embeds; if it inlines user-specific data, cache the response anyway (it's the
  same single-household device) but confirm nothing breaks when a different user
  of the same browser logs in — worst case the shell re-renders on first online
  navigation. Note this in the PR.
- The existing pytest suite has `tests/test_static_assets.py` — extend it: assert
  `/sw.js` still serves with `Service-Worker-Allowed: /` and that the file
  contains the `install` listener (cheap regression guard).

## Acceptance criteria

- `python3 -m pytest` passes, including the extended static-asset test.
- Manual (document with steps in the PR — Chrome DevTools):
  1. Load app logged-in → Application tab shows `remndrs-shell-v1` with the 5
     shell URLs; SW active.
  2. DevTools → Network → Offline → reload: app opens (shell), notes list may be
     empty/stale — no white screen.
  3. Still offline: create a note → composer closes, "queued" indicator shows 1,
     IndexedDB `remndrs-outbox` has the row.
  4. Network back online (toggle) → within a second (online event) the note
     POSTs, appears in the feed (SSE), outbox is empty, indicator clears.
  5. Offline, submit a note while logged OUT (or force a 400) → error surfaces,
     nothing queued.
  6. SSE still works after all changes: two tabs, note created in one appears in
     the other.
