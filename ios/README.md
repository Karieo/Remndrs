# Remndrs iOS

SwiftUI companion app for the Remndrs Mac server. Quick capture (text, voice,
photos), a share extension for Safari/Photos, the feed in the brand design,
"send anywhere" (SMS / email / calendar), and reminders as local notifications.

The visual design comes from the Claude Design handoff (`Remndrs iOS.html`):
warm dark palette, Playfair Display / Lora / IBM Plex Mono type, channel chips,
gold accent. Fonts are bundled (all SIL OFL licensed).

## Building (on your Mac)

The Xcode project is generated, not checked in:

```bash
brew install xcodegen
cd ios
xcodegen            # generates Remndrs.xcodeproj from project.yml
open Remndrs.xcodeproj
```

Then in Xcode, one-time setup:

1. Select the **Remndrs** target → Signing & Capabilities → set your **Team**.
   Do the same for the **RemndrsShare** target.
2. If the bundle id `com.remndrs.*` collides with someone else's, change
   `bundleIdPrefix` in `project.yml` (and the two ids in
   `Shared/AppGroup.swift` to match), then re-run `xcodegen`.
3. Xcode will register the App Group (`group.com.remndrs.app`) and keychain
   access group automatically with automatic signing.
4. Build & run on your iPhone. For installs that outlast 7 days, Archive →
   distribute via TestFlight.

## Signing in

The app talks to your Mac server through its Cloudflare Tunnel URL
(see `CLOUDFLARE_SETUP.md` in the repo root). On first launch enter:

- **Server URL** — e.g. `https://remndrs.yourdomain.com`
- Your Remndrs name/email and password

This calls `POST /api/auth/token` and stores a long-lived token in the
keychain (shared with the extension via the keychain access group).

## What's where

```
project.yml           XcodeGen spec — app + share extension targets
Shared/               compiled into both targets
  Theme.swift         design palette, fonts, channel colors
  Models.swift        API models (Note, Reminder, …)
  APIClient.swift     async URLSession client, multipart
  CredentialsStore.swift  keychain (shared access group)
Remndrs/              the app
  Views/              Feed, Composer, Capture (voice), SendSheet, Login, Settings
  ReminderSyncer.swift  server reminders → UNUserNotificationCenter
RemndrsShare/         share extension (URL / text / image → note)
```

## Known limits (v1)

- Reminders created on the server between syncs that fire before the next
  sync won't raise a local notification (SMS/web still fire server-side).
  Sync runs on app open, via background refresh, and from Settings.
- No offline queue: saving a note with no connectivity shows an error and
  keeps your text in the composer.
- While the app is open it holds an SSE connection to `/api/stream`, so new
  notes and replies appear live (`SSEClient.swift`). In the background it
  falls back to BGAppRefreshTask reminder sync only.
