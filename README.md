# Remndrs

A personal productivity and note-taking platform: an always-active, text-based
personal inbox. Capture thoughts, ideas, reminders, images, links, and voice
memos from anywhere — web UI, SMS, email, or a phone call — and everything
lands in a single searchable, tagged feed rendered as markdown.

Every note is a real `.md` file stored in iCloud Drive. The app is a view over
those files. If the app disappeared tomorrow, every note would still be
readable in Finder, Obsidian, or any text editor.

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

To stop the app and remove auto-start: `./uninstall.sh` (add `--purge` to also
wipe the database and config — your notes in iCloud are never touched).

The app always starts, even with no integrations configured. Twilio, OpenAI,
Mailgun, and CalDAV features each enable themselves only when their
credentials are present in `.env`.

## Notes Folder

Notes are written to `~/Library/Mobile Documents/com~apple~CloudDocs/Remndrs/`
(configurable via `NOTES_FOLDER` in `.env`):

```
Remndrs/
  Clay/                 ← your private notes
    attachments/        ← photos, files from MMS/email/uploads
    Calendar/           ← calendar event stubs
  Shared/               ← notes both users can see
```

If iCloud Drive is unavailable, Remndrs falls back to `~/Documents/Remndrs/`.

## Integrations Setup

### Twilio (SMS + Voice)

1. Go to [twilio.com](https://www.twilio.com) and create a free account
2. Verify your phone number during signup
3. From the Console Dashboard, note your **Account SID** and **Auth Token**
4. Go to Phone Numbers → Manage → Buy a Number (~$1.15/month)
5. Under the number's settings:
   - "A Message Comes In" → Webhook (HTTP POST): `https://your-tunnel-url/webhooks/sms`
   - "A Call Comes In" → Webhook: `https://your-tunnel-url/webhooks/voice/answer`
6. Add `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `OWNER_PHONE_NUMBER` to `.env`
7. Set the Twilio number on your user row (`twilio_number` in the users table)

**SMS commands** (text these to your Twilio number):

| Command | What it does |
|---|---|
| `GET groceries` | Texts back your 3 most recent notes tagged #GROCERIES |
| `FIND keyword` | Full-text search, top 3 matches |
| `LIST` | Your 5 most recent notes |
| `REMIND ME tomorrow at 3pm to call the dentist` | Sets a reminder |
| anything else | Saved as a note (auto-tagged #SMS; `#SHARED` routes to the shared feed) |

Calling your Twilio number records a voice memo, transcribes it via Whisper,
and saves it as a note tagged #VOICE.

### OpenAI (Voice transcription)

Add `OPENAI_API_KEY` to `.env`. This enables the microphone/upload button in
the composer and transcription of phone-call recordings. Audio files are
limited to 25MB (Whisper's limit).

### Mailgun (Email inbound)

Requires a custom domain (Mailgun's sandbox domain works for testing only).

1. Go to [mailgun.com](https://www.mailgun.com) and create a free account
   (5,000 emails/month free)
2. Add and verify your domain
3. Under Receiving → Create Route:
   - Filter: `match_recipient("notes@yourdomain.com")`
   - Action: `forward("https://your-tunnel-url/webhooks/email")` and `store()`
4. Add `MAILGUN_API_KEY` and `MAILGUN_SIGNING_KEY` (HTTP webhook signing key)
   to `.env`
5. Inbound mail is routed by **recipient address** — set each user's
   `users.email` to the address their notes are sent to

Subject becomes the bolded first line. `[shared]` in the subject routes to
the shared feed. `#HASHTAGS` and `[BRACKETED]` subject prefixes become tags.
Attachments are saved to iCloud and linked from the note.

**Tagging from the email body** — three ways:

- `Tags: groceries, costco` on its own line (the line is removed from the note)
- A line of just hashtags: `#ideas #reading` (also removed)
- Inline `#hashtags` anywhere in the text (tagged, text kept as-is)

`Tags: shared` (or `#SHARED`) routes the note to the shared feed, same as SMS.

**Email reminders:** forward any email and put a remind phrase with a time
in the subject — or as the first line you type above the forwarded content:

- `Remind me tomorrow at 9am — pay this invoice`
- `Reminder: dentist next Tuesday at noon`
- Subject `Fwd: Invoice #123`, first body line `remind me Friday at 3pm`

The email is saved as a note (tagged #REMINDER) and a linked reminder fires
via web banner, SMS, and the iOS app. If outbound email is configured you
get a confirmation reply with the parsed time.

### iCloud Calendar (CalDAV)

iCloud CalDAV requires an **app-specific password** — never your main Apple ID
password:

1. Go to [appleid.apple.com](https://appleid.apple.com)
2. Sign in → Security → App-Specific Passwords → Generate
3. Label it "Remndrs"
4. Copy the generated password into `.env` as `CALDAV_PASSWORD`
5. Set `CALDAV_USERNAME` to your Apple ID email address
6. `CALDAV_URL` is always `https://caldav.icloud.com` — never change this

Then open the `···` settings panel in the app, enable the calendars you want,
and choose Private or Shared for each. Sync runs every 10 minutes (or use
"Sync now"). Events appear as cards in the feed (past 7 days, next 30). You
can attach notes to events — they never modify the event in Apple Calendar —
and turn notes into iCloud events from the card menu.

### Cloudflare Tunnel (mobile access + webhooks)

See [CLOUDFLARE_SETUP.md](CLOUDFLARE_SETUP.md).

## Adding a second user

There's deliberately no admin UI. Create the account from the app directory:

```bash
python3 -c "
import bcrypt, database as db
db.create_user('Mia', bcrypt.hashpw(b'her-password', bcrypt.gensalt()).decode(),
               email='mia@example.com')"
```

They log in with that name/password. Once a second user exists, the card menu's
**Share with…** sends a note to them — it lands in their Shared feed with your
name on it, and either of you can reply in the thread on the card. Replies are
also appended to the note's `.md` file under a `## Replies` heading.

## Auto-start on login

`setup.sh` installs `com.remndrs.plist` into `~/Library/LaunchAgents` so the
app starts when you log in to your Mac. Logs go to `/tmp/remndrs.log`.
