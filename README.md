# Remndrs

A personal productivity and note-taking platform: an always-active, text-based
personal inbox. Capture thoughts, ideas, reminders, images, links, and voice
memos from anywhere — web UI, iPhone app, SMS, email, or a phone call — and
everything lands in a single searchable, tagged feed rendered as markdown.

Every note is a real `.md` file stored in iCloud Drive. The app is a view over
those files. If the app disappeared tomorrow, every note would still be
readable in Finder, Obsidian, or any text editor.

**Guiding principles**

- **Local first.** The app runs on your Mac. Your data never goes to a
  third-party database.
- **Plain files.** Every note is a `.md` file in iCloud. The app is
  disposable; the files are not.
- **Never crash on missing config.** Every integration enables itself only
  when its credentials exist — the app always starts.

---

## Contents

- [Features at a glance](#features-at-a-glance)
- [Install on your Mac](#install-on-your-mac)
- [Using the app](#using-the-app)
  - [The feed](#the-feed)
  - [Writing notes](#writing-notes)
  - [Reminders](#reminders)
  - [Send a note anywhere](#send-a-note-anywhere)
  - [Sharing with another person](#sharing-with-another-person)
  - [Calendar](#calendar)
- [Capture channels](#capture-channels)
  - [SMS](#sms)
  - [Voice calls](#voice-calls)
  - [Email](#email)
  - [iPhone app](#iphone-app)
- [Your data](#your-data)
- [Integrations setup](#integrations-setup)
- [Adding a second user](#adding-a-second-user)
- [Remote access (phone, webhooks)](#remote-access-phone-webhooks)
- [Configuration reference](#configuration-reference)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Uninstall](#uninstall)

---

## Features at a glance

| | |
|---|---|
| **Capture** | Web composer, iPhone app + share sheet, SMS/MMS, email forwarding, voice calls transcribed by Whisper |
| **Organize** | Global colored tags, full-text search, channel filters, pinning, to-do lists with progress |
| **Send back out** | Push any note to SMS, email, or an iCloud calendar event |
| **Share** | Person-to-person sharing with reply threads |
| **Remind** | Natural-language reminders from SMS or email; web banners, SMS, and iOS notifications |
| **Calendar** | Two-way iCloud Calendar sync; attach notes to events without touching the event |
| **Own your data** | Every note is an Obsidian-compatible `.md` file in iCloud Drive |
| **Real-time** | Open tabs and the iPhone app update live (Server-Sent Events) |

---

## Install on your Mac

**One-liner** (Terminal):

```bash
curl -fsSL https://raw.githubusercontent.com/Karieo/Remndrs/main/install.sh | bash
```

That clones the app into `~/remndrs`, sets up an isolated Python environment,
generates secrets, asks you to pick your name and password, installs
auto-start on login, starts the app, and opens it in your browser.

**Prefer Finder?** Download the repo, double-click `Install Remndrs.command`.

**Already cloned it?**

```bash
cd ~/remndrs && ./setup.sh
```

`setup.sh` is safe to re-run any time — it updates dependencies and keeps your
`.env`, database, and notes. The only prerequisite is Apple's Command Line
Tools (macOS offers to install them automatically the first time `git` or
`python3` runs).

Works on both **Apple Silicon and Intel** Macs (Python 3.9+). All compiled
dependencies install as prebuilt wheels for either architecture, and if you
ever migrate the app folder between Macs (Intel → M-series), `setup.sh`
detects the architecture mismatch and rebuilds the environment automatically.

The app always starts, even with no integrations configured. Twilio, OpenAI,
Mailgun, and CalDAV features each enable themselves only when their
credentials are present in `.env`.

After install the app runs at **http://localhost:3000** (it falls back to
3001/3002 if the port is busy) and restarts automatically whenever you log in
to your Mac.

---

## Using the app

### The feed

The main screen is a masonry grid of cards, newest first, pinned notes on top.

- **Mine / Shared** — the toggle in the header switches between your private
  feed and the shared feed both users can see. The badge shows how many
  shared notes exist.
- **Channel filter** — the rail under the search box filters by where a note
  came from: All · SMS · Voice · Email · Calendar · App. Every card carries a
  colored channel chip so you always know how a note arrived.
- **Tags** — the tag bar lists every tag with its color; click to filter
  (multiple tags = OR). `+ Add Tag` creates one with a palette picker;
  `# Edit Tags` renames, recolors, or deletes (notes are never deleted with a
  tag). A note's **first tag drives the card's accent color**.
- **Search** — full-text across all your notes, debounced as you type.
- **Theme** — sun/moon button toggles warm-dark / warm-light; remembered per
  browser.
- **Live updates** — a note texted in from your phone appears in the open tab
  within seconds, no refresh.

**Keyboard shortcuts**

| Key | Action |
|---|---|
| `N` | New note |
| `⌘↵` | Save (composer open) |
| `Esc` | Close any sheet/menu |
| `/` | Focus search |

### Writing notes

Press `N` or the gold `+`. The composer has two modes:

- **Note** — freeform markdown. Type `#hashtags` anywhere; they're extracted
  live (shown in the tag preview row, marked "new" if they don't exist yet)
  and stripped from the saved text. New tags get a palette color
  automatically.
- **To-Do** — first line is the title, every following line becomes a
  checkbox item. Cards show an `n / m` progress bar; check items off right on
  the card.

A Private/Shared toggle picks the feed, and the optional **⏰ remind me** row
attaches a reminder to the note as you save it.

### Reminders

Create them from the composer, by SMS (`REMIND ME …`), or by emailing a
remind phrase (see [Email](#email)). When a reminder fires you get, all at
once:

- a persistent banner in any open web tab (dismissable, stays dismissed),
- an SMS to your phone (if Twilio is configured),
- an iOS notification (if the app is installed — synced even in background).

### Send a note anywhere

Every card's `···` menu can push the note back out:

- **Send via SMS** — texts the note's content (to you by default, or any
  number).
- **Send via Email** — emails it via Mailgun (to you by default, or any
  address).
- **Add to Calendar** — pick an iCloud calendar and time; the note becomes a
  real calendar event (first line = title, full text = description).

Plus quick actions: **Copy text**, **Pin to top**, **Move to Shared/Mine**,
**Delete**.

### Sharing with another person

With a second user set up (see [Adding a second user](#adding-a-second-user)):

- `···` → **Share with…** opens a person picker with an optional message.
- The note lands in the **Shared** feed for both of you, with the sender's
  avatar, name, and direction ("shared with you" / "you shared with Mia" —
  outgoing cards get a dashed accent).
- Either person can **reply** in a thread right on the card; your replies
  appear as right-aligned gold bubbles. The share message reads as the
  opening bubble.
- Replies are also appended to the note's `.md` file under a `## Replies`
  heading, so the conversation lives in your files too.

### Calendar

With CalDAV configured (see [setup](#icloud-calendar-caldav)), events from
your enabled iCloud calendars appear as purple-spine cards in the feed —
the past 7 days (dimmed) and next 30. On each event card:

- **+ Add note to this event** — attach freeform markdown. It's stored in
  Remndrs and the event's `.md` stub only; **the event in Apple Calendar is
  never modified**.
- Events you edit in Apple Calendar update here within 10 minutes ("Sync
  now" in settings forces it). Events deleted in Apple Calendar are marked
  **orphaned**, never silently removed.

The ⚙ settings sheet controls which calendars are enabled and whether each
feeds Private or Shared.

---

## Capture channels

### SMS

Text your dedicated Twilio number ([setup](#twilio-sms--voice)). Plain texts
become notes instantly (auto-tagged `#SMS`; photos/MMS attach to the note and
render on the card). Commands:

| Command | What it does |
|---|---|
| `GET groceries` | Texts back your 3 most recent notes tagged #GROCERIES |
| `FIND keyword` | Full-text search, top 3 matches |
| `LIST` | Your 5 most recent notes |
| `REMIND ME tomorrow at 3pm to call the dentist` | Sets a reminder, confirms the parsed time |
| anything else | Saved as a note — `#hashtags` become tags, `#SHARED` routes to the shared feed |

### Voice calls

Call your Twilio number. It beeps, records until you hang up (5 min max),
transcribes via Whisper, cleans the filler words, and saves the note tagged
`#VOICE` — then texts you a confirmation with the first line. Say
"hashtag ideas" or "tag this as ideas" mid-recording to tag it; say "shared"
to route it to the shared feed. The note appears in the web feed in real time.

(In-app voice capture lives in the iPhone app's Capture tab — record, get
the transcript in the composer, edit, save.)

### Email

Email (or forward anything to) your Mailgun inbound address
([setup](#mailgun-email-inbound)). The subject becomes the bolded first
line; attachments save to iCloud and render on the card.

**Tagging from the email body** — three ways:

- `Tags: groceries, costco` on its own line (the line is removed from the note)
- A line of just hashtags: `#ideas #reading` (also removed)
- Inline `#hashtags` anywhere in the text (tagged, text kept as-is)

`[shared]` in the subject, `Tags: shared`, or `#SHARED` routes to the
shared feed. `[BRACKETED]` subject prefixes become tags too.

**Email reminders:** put a remind phrase with a time in the subject — or as
the first line you type above the forwarded content:

- `Remind me tomorrow at 9am — pay this invoice`
- `Reminder: dentist next Tuesday at noon`
- Subject `Fwd: Invoice #123`, first body line `remind me Friday at 3pm`

The email is saved as a note (tagged `#REMINDER`) and a linked reminder
fires via web banner, SMS, and the iOS app. If outbound email is configured
you get a confirmation reply with the parsed time.

### iPhone app

A native SwiftUI companion in [`ios/`](ios/README.md) — quick capture, the
feed in the brand design, voice memos (record → Whisper → composer), photo
attach, the send sheet, shared-feed reply threads, and reminder
notifications. Plus a **share extension**: send any page, text, or image to
Remndrs from Safari/Photos via the system share sheet, with a link preview,
note field, tags, and an optional straight-to-calendar save.

Build it on your Mac (needs Xcode + a free `brew install xcodegen`):

```bash
cd ~/remndrs/ios && xcodegen && open Remndrs.xcodeproj
```

Set your signing team on both targets and run. Full steps, signing notes,
and TestFlight guidance: [`ios/README.md`](ios/README.md). The app signs in
with your server URL (your Cloudflare Tunnel address) and the same
name/password as the web.

---

## Your data

### Where notes live

`~/Library/Mobile Documents/com~apple~CloudDocs/Remndrs/` (configurable via
`NOTES_FOLDER` in `.env`):

```
Remndrs/
  Clay/                 ← your private notes
    attachments/        ← photos & files from MMS/email/uploads
    Calendar/           ← calendar event stubs
  Mia/                  ← second user's private notes
  Shared/               ← notes everyone can see
```

If iCloud Drive is unavailable, Remndrs falls back to `~/Documents/Remndrs/`
(with a logged warning) rather than failing.

### File format

Obsidian-compatible markdown with YAML frontmatter. Open the folder as an
Obsidian vault and it just works:

```markdown
---
id: 550e8400-e29b-41d4-a716-446655440000
user: Clay
feed: private
tags: [REMNDRS, MARKETING]
tag_colors: {REMNDRS: "#4ade80", MARKETING: "#f87171"}
source: sms
pinned: false
created: 2026-05-24T11:30:00
updated: 2026-05-24T11:30:00
---

SMS Retrieval Feature — text commands that pull up your notes via SMS reply.
```

To-do items render as `- [ ]` / `- [x]` checklists; replies append under a
`## Replies` heading; calendar stubs keep regenerated frontmatter above a
marker comment and preserve everything you write below it.

### Database, backup, reset

- The SQLite database (`data/remndrs.db`) holds the index: tags, todos,
  reminders, shares, calendar state. The `.md` files hold the content.
- **Backup** = your iCloud folder (already synced) plus, optionally,
  `data/remndrs.db` and `.env`.
- **Reset the app** without losing notes: stop it and delete
  `data/remndrs.db` — the owner account is re-seeded from `.env` on next
  start. (Existing `.md` files aren't re-imported; the DB is the index.)
- Deleting a note from the app deletes its `.md` file too. Deleting a tag
  never deletes notes.

---

## Integrations setup

Each of these is optional and independent. **Configure everything in the app**:
open ⚙ → **Integrations**, paste the credentials, hit **Save** then **Test** —
changes apply immediately, no restart, no file editing. (They're stored in the
app's `.env`, so editing that file by hand still works too.)

The ⚙ → **Webhooks** tab shows the exact URLs to paste into the Twilio and
Mailgun consoles once you've saved your public tunnel URL. The ⚙ → **People**
tab is where you set your own routing (your mobile number, your Remndrs
Twilio number, your inbound email address).

What each provider needs:

### Twilio (SMS + Voice)

1. Go to [twilio.com](https://www.twilio.com) and create a free account
2. Verify your phone number during signup
3. From the Console Dashboard, note your **Account SID** and **Auth Token**
4. Go to Phone Numbers → Manage → Buy a Number (~$1.15/month)
5. Under the number's settings, paste the URLs from ⚙ → Webhooks:
   - "A Message Comes In" → Webhook (HTTP POST): the **SMS** URL
   - "A Call Comes In" → Webhook: the **Call answer** URL
6. In ⚙ → Integrations → Texts & calls: paste the **Account SID**, **Auth
   token**, and your mobile number → Save → Test
7. In ⚙ → People: set **Remndrs #** to the Twilio number you bought, so
   inbound texts route to you

All webhooks verify Twilio's signature — unsigned requests are rejected.

### OpenAI (Voice transcription)

Paste an API key in ⚙ → Integrations → Voice transcription. This enables
transcription of phone-call recordings and the iPhone app's voice capture.
Audio is limited to 25MB (Whisper's limit — roughly 45+ minutes at phone
quality).

### Mailgun (Email inbound)

Requires a custom domain (Mailgun's sandbox domain works for testing only).

1. Go to [mailgun.com](https://www.mailgun.com) and create a free account
   (5,000 emails/month free)
2. Add and verify your domain
3. Under Receiving → Create Route:
   - Filter: `match_recipient("notes@yourdomain.com")`
   - Action: `forward("https://your-tunnel-url/webhooks/email")` and `store()`
   (the forward URL is the **Email** one from ⚙ → Webhooks)
4. In ⚙ → Integrations → Email: paste the **API key**, **webhook signing
   key**, and the inbound address from step 3 → Save → Test
5. Inbound mail is routed by **recipient address** — set your **Email** in
   ⚙ → People to the address your notes are sent to

The API key + inbound address also enable **outbound** email: the "Send via
Email" action and reminder confirmation replies.

### iCloud Calendar (CalDAV)

iCloud CalDAV requires an **app-specific password** — never your main Apple ID
password:

1. Go to [appleid.apple.com](https://appleid.apple.com)
2. Sign in → Security → App-Specific Passwords → Generate
3. Label it "Remndrs"
4. In ⚙ → Integrations → iCloud Calendar: enter your Apple ID email and the
   generated password → Save → Test (it should report your calendars)

Then in ⚙ → Calendars, enable the ones you want and choose Private or Shared
for each. Sync runs every 10 minutes (or use "Sync now").

---

## Adding a second user

⚙ → **People** → "Add a person": name, password, optional email. Done.

They log in with that name/password (web and iPhone app) and set their own
mobile number / inbound email under their own ⚙ → People. Once a second user
exists:

- the **Share with…** picker finds them automatically,
- notes either of you mark Shared appear in both Shared feeds,
- a calendar you both enable and set to Shared shows its events to both,
- their own email address / Twilio number can be set on their user row for
  their own capture channels.

---

## Remote access (phone, webhooks)

The app listens on `localhost` only. To reach it from your phone — and to
give Twilio/Mailgun a webhook target — put a free Cloudflare Tunnel in front
of it: no open router ports, HTTPS, works anywhere.

Full walkthrough: [CLOUDFLARE_SETUP.md](CLOUDFLARE_SETUP.md).

Web sessions use cookies (7-day life); the iPhone app exchanges your
password for a long-lived token kept in the keychain. Webhook routes skip
sessions entirely and verify provider signatures instead.

---

## Configuration reference

Everything lives in `.env` (created from `.env.example` by the installer):

| Variable | Required | Purpose |
|---|---|---|
| `SESSION_SECRET` | yes (generated) | Signs login cookies |
| `OWNER_NAME` / `OWNER_PASSWORD` | yes (prompted) | Seeds the owner account on first run |
| `NOTES_FOLDER` | no | Where `.md` files go (default: iCloud Drive `Remndrs/`) |
| `PORT` | no | Default 3000; falls back to 3001/3002 if busy |
| `ENCRYPTION_KEY` | yes (generated) | Encrypts stored CalDAV passwords (Fernet) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | for SMS/voice | Twilio credentials |
| `OWNER_PHONE_NUMBER` | for SMS replies | Your real mobile number |
| `OPENAI_API_KEY` | for voice | Whisper transcription |
| `MAILGUN_API_KEY` | for email out | Mailgun API key |
| `MAILGUN_SIGNING_KEY` | for email in | Webhook signature verification |
| `MAILGUN_INBOUND_ADDRESS` | for email | The address notes are sent to (also the outbound from-address) |
| `CALDAV_USERNAME` / `CALDAV_PASSWORD` | for calendar | Apple ID + app-specific password |
| `CALDAV_URL` | no | Always `https://caldav.icloud.com` |

---

## Architecture

| Layer | Technology |
|---|---|
| Backend | Python 3 + Flask, one process |
| Database | SQLite (built-in `sqlite3`, FTS5 full-text search) |
| Real-time | Server-Sent Events — every open tab/device gets every event |
| Scheduling | APScheduler (reminders every 60s, calendar sync every 10min) |
| Frontend | Vanilla HTML/CSS/JS + marked.js — no build step |
| iOS | SwiftUI, XcodeGen project, bearer-token auth |
| Files | Plain `.md` written alongside every DB write |

Module layout (one file per concern, `app.py` holds all routes):

```
app.py             Flask routes, auth, SSE stream, webhooks
database.py        schema + every query (SQLite, FTS5)
files.py           .md file mirroring (frontmatter, stubs, replies)
sse.py             per-connection event queues
reminders.py       scheduler + natural-language time parsing
sms.py             Twilio inbound commands, replies, MMS
voice.py           Whisper transcription + transcript cleanup
email_inbound.py   Mailgun webhook, tags, reminders, outbound send
calendar_sync.py   CalDAV two-way sync, orphan detection
attachments.py     file saving/serving for every channel
templates/ static/ the web UI
ios/               the iPhone app (see ios/README.md)
```

Key invariant: **any code path that creates or changes a note writes the
`.md` file and pushes an SSE event** — webhooks included. The DB is the
index; the files are the truth.

---

## Troubleshooting

**Is it running?**
`curl -s localhost:3000/login -o /dev/null -w '%{http_code}'` → `200`.
Logs: `/tmp/remndrs.log` and `/tmp/remndrs.err.log`.

**Restart it**
`launchctl kickstart -k gui/$(id -u)/com.remndrs` — or unload/load the plist
in `~/Library/LaunchAgents`.

**Wrong port?** If 3000 was busy at startup the app moved to 3001/3002 — the
log's first lines say which.

**Notes appearing in `~/Documents/Remndrs` instead of iCloud** — iCloud
Drive isn't enabled (System Settings → Apple ID → iCloud → Drive). The app
falls back rather than failing; move the files and they'll pick up in the
right place once iCloud Drive exists.

**SMS/voice webhooks return 403** — signature verification failed. Almost
always: the webhook URL in the Twilio console doesn't exactly match the
public URL (scheme/host/path), or `TWILIO_AUTH_TOKEN` is wrong.

**Voice transcription returns 503** — `OPENAI_API_KEY` isn't set.

**Calendar settings show no calendars** — check `CALDAV_USERNAME` /
`CALDAV_PASSWORD` (must be an app-specific password) and that the Mac can
reach `caldav.icloud.com`.

**Email creates no note** — the recipient address must match a user's
`email` column exactly; check `MAILGUN_SIGNING_KEY` (403s are logged).

**Start fresh** — stop the app, `rm data/remndrs.db`, start. Owner account
re-seeds from `.env`; your `.md` notes are untouched (but not re-imported —
the DB is the index).

**iPhone app says session expired** — sign out and back in (Settings tab);
tokens are revocable server-side.

---

## Uninstall

```bash
cd ~/remndrs && ./uninstall.sh          # stop the app, remove auto-start
cd ~/remndrs && ./uninstall.sh --purge  # also wipe venv, database, .env
```

Your notes in iCloud are **never** touched by either. After `--purge`,
delete the folder itself with `rm -rf ~/remndrs` if you want it gone
completely.
