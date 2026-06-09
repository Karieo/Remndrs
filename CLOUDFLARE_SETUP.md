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

Requires a free Cloudflare account and a domain on Cloudflare.

```bash
cloudflared tunnel login
cloudflared tunnel create remndrs
cloudflared tunnel route dns remndrs remndrs.yourdomain.com
```

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: remndrs
credentials-file: /Users/YOU/.cloudflared/<TUNNEL-ID>.json
ingress:
  - hostname: remndrs.yourdomain.com
    service: http://localhost:3000
  - service: http_status:404
```

Run it as a service so it starts on login:

```bash
sudo cloudflared service install
```

## 4. Point webhooks at the tunnel

- Twilio SMS: `https://remndrs.yourdomain.com/webhooks/sms`
- Twilio voice answer: `https://remndrs.yourdomain.com/webhooks/voice/answer`
- Twilio recording callback: `https://remndrs.yourdomain.com/webhooks/voice`
- Mailgun route: `https://remndrs.yourdomain.com/webhooks/email`

The app itself is protected by login; webhook routes verify provider
signatures instead of sessions.
