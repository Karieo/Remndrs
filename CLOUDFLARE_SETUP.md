# Cloudflare Tunnel Setup

Make your local Remndrs instance reachable from your phone (and from Twilio /
Mailgun webhooks) without opening any router ports.

## 1. Install cloudflared

```bash
brew install cloudflared
```

## 2. Quick tunnel (testing)

```bash
cloudflared tunnel --url http://localhost:3000
```

This prints a random `https://*.trycloudflare.com` URL. Good for testing, but
the URL changes every run — don't use it for webhooks.

## 3. Named tunnel (permanent)

Requires a free Cloudflare account and a domain **added to Cloudflare** (its
nameservers pointing at Cloudflare — check the dashboard says "Active", not
"Pending Nameserver Update").

```bash
cloudflared tunnel login
cloudflared tunnel create remndrs
cloudflared tunnel route dns remndrs remndrs.example.com
```

Create `~/.cloudflared/config.yml` — this one command fills in the paths for
you, so you only edit the hostname:

```bash
cat > ~/.cloudflared/config.yml <<EOF
tunnel: remndrs
credentials-file: $(ls ~/.cloudflared/*.json | head -1)
ingress:
  - hostname: remndrs.example.com
    service: http://localhost:3000
  - service: http_status:404
EOF
```

Test it in the foreground first — this should print "Registered tunnel
connection" lines and the site should load:

```bash
cloudflared tunnel run remndrs
```

Visit your hostname. Once the Remndrs login appears, `Ctrl-C` and install it
as a background service (next section).

### Gotcha A — `route dns` fails with "record … already exists" (error 1003)

Your apex/subdomain already has a parked DNS record (common with new domains —
a registrar parking-page `A` record). Delete it: Cloudflare dashboard →
your domain → DNS → Records → find the `A`/`CNAME` row for that hostname →
Edit → Delete. Then re-run the `route dns` command. (Your `MX`/`TXT` email
records are a different type and can stay — they coexist with the tunnel.)

### Gotcha B — page shows Cloudflare "Error 1033"

DNS is working but the tunnel has no active connection. `cloudflared tunnel
info <name>` will say "does not have any active connection." Make sure
`cloudflared tunnel run remndrs` is actually running (foreground test above),
or that the service is correctly installed (next section — the default
installer often generates a broken service).

## 4. Run it as a background service

```bash
sudo cloudflared service install
```

**Important — verify it actually connected:**

```bash
sleep 8 && sudo cloudflared tunnel info remndrs
```

If that shows active connections, you're done. If it says **"does not have
any active connection"** even though the foreground `tunnel run` worked, the
installer generated a broken service (a known macOS issue — the plist runs
`cloudflared` with no arguments). Fix it by overwriting the plist's command.

Find your cloudflared path and username first:

```bash
which cloudflared   # e.g. /usr/local/bin/cloudflared (Intel) or /opt/homebrew/bin/cloudflared (Apple Silicon)
whoami              # your username, e.g. clay
```

Then write a correct plist (substitute the binary path and
`/Users/<you>/.cloudflared/config.yml`):

```bash
sudo tee /Library/LaunchDaemons/com.cloudflare.cloudflared.plist > /dev/null <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cloudflare.cloudflared</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/cloudflared</string>
        <string>--no-autoupdate</string>
        <string>--config</string>
        <string>/Users/clay/.cloudflared/config.yml</string>
        <string>tunnel</string>
        <string>run</string>
        <string>remndrs</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Library/Logs/com.cloudflare.cloudflared.out.log</string>
    <key>StandardErrorPath</key>
    <string>/Library/Logs/com.cloudflare.cloudflared.err.log</string>
    <key>KeepAlive</key>
    <dict><key>SuccessfulExit</key><false/></dict>
    <key>ThrottleInterval</key>
    <integer>5</integer>
</dict>
</plist>
EOF

sudo launchctl unload /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
sudo launchctl load /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
sleep 8 && sudo cloudflared tunnel info remndrs
```

Now it shows active connections, survives reboots, and needs no open terminal.

If `service install` says it's "already installed," clean it first with
`sudo cloudflared service uninstall`, then reinstall (or just overwrite the
plist as above).

## 5. Point webhooks at the tunnel

- Twilio SMS: `https://remndrs.example.com/webhooks/sms`
- Twilio voice answer: `https://remndrs.example.com/webhooks/voice/answer`
- Twilio recording callback: `https://remndrs.example.com/webhooks/voice`
- Mailgun route: `https://remndrs.example.com/webhooks/email`

The ⚙ → Webhooks tab in the app generates these exact URLs once you save your
public URL — copy them straight into the Twilio/Mailgun consoles.

The app itself is protected by login; webhook routes verify provider
signatures instead of sessions.
