# Raspberry Pi Setup

Run Remndrs on an always-on Raspberry Pi instead of your Mac — no more
outages when the laptop sleeps or leaves the house. Total time: ~45 min.

**Works on:** Pi 3, 4, 5, or Zero 2 W (anything ARMv7/ARM64).
**Doesn't work on:** original Pi 1 / Pi Zero (ARMv6 — cloudflared has no
official build). Check yours: `cat /proc/device-tree/model` on the Pi, or
look at the board silkscreen.

## 1. Flash the Pi

1. Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) on the Mac.
2. Choose **Raspberry Pi OS Lite (64-bit)** (no desktop needed).
3. Click the ⚙ / "Edit settings" before writing: set hostname `remndrs-pi`,
   enable **SSH**, set username `pi` + a password, and add your Wi-Fi.
4. Write the SD card, boot the Pi, then from the Mac: `ssh pi@remndrs-pi.local`

## 2. Install the app

On the Pi:

```bash
sudo apt update && sudo apt install -y git python3-venv python3-pip
git clone https://github.com/Karieo/Remndrs.git ~/Remndrs
cd ~/Remndrs
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## 3. Move your data over

On the **Mac** (stop the app first so the DB isn't mid-write):

```bash
launchctl bootout gui/$(id -u)/com.remndrs
scp ~/Remndrs/.env ~/Remndrs/data/remndrs.db pi@remndrs-pi.local:~/Remndrs/
ssh pi@remndrs-pi.local 'mkdir -p ~/Remndrs/data && mv ~/Remndrs/remndrs.db ~/Remndrs/data/'
scp -r ~/Remndrs/uploads pi@remndrs-pi.local:~/Remndrs/ 2>/dev/null || true
```

On the **Pi**, point the notes folder somewhere local (no iCloud on Linux)
and pin the port:

```bash
cd ~/Remndrs
sed -i '/^NOTES_FOLDER=/d;/^PORT=/d' .env
echo "NOTES_FOLDER=/home/pi/RemndrsNotes" >> .env
echo "PORT=3000" >> .env
```

## 4. Run it as a service (systemd)

```bash
sudo tee /etc/systemd/system/remndrs.service > /dev/null <<'EOF'
[Unit]
Description=Remndrs
After=network-online.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/Remndrs
ExecStart=/home/pi/Remndrs/venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now remndrs
sleep 3 && curl -s localhost:3000/api/version   # should print the version JSON
```

## 5. Move the tunnel

Reuse the tunnel you already created — just copy its credentials:

On the **Mac** (stop the Mac's tunnel first so they don't both serve):

```bash
sudo launchctl bootout system/com.cloudflare.cloudflared
scp ~/.cloudflared/cert.pem ~/.cloudflared/*.json ~/.cloudflared/config.yml pi@remndrs-pi.local:~/
```

On the **Pi**:

```bash
mkdir -p ~/.cloudflared && mv ~/cert.pem ~/*.json ~/config.yml ~/.cloudflared/
# fix the credentials path inside config.yml for the new home dir
sed -i 's#/Users/[^/]*/.cloudflared#/home/pi/.cloudflared#' ~/.cloudflared/config.yml

# install cloudflared (ARM64 build)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o /tmp/cf.deb
sudo dpkg -i /tmp/cf.deb

# install as a service — on Linux this generates a CORRECT systemd unit
# (unlike the broken macOS plist), pointing at your config:
sudo cloudflared --config /home/pi/.cloudflared/config.yml service install
sleep 8 && cloudflared tunnel info remndrs   # should show active connections
```

Load `https://remndrs.app` on your phone — it should be up, served by the Pi.

> 32-bit OS? Use `cloudflared-linux-armhf.deb` instead of `arm64`.

## 6. Get the .md files back into iCloud/Obsidian (optional)

The Pi writes notes to `/home/pi/RemndrsNotes`. To mirror them into your
Mac's iCloud Drive Obsidian vault, install [Syncthing](https://syncthing.net)
on both:

```bash
# Pi
sudo apt install -y syncthing
sudo systemctl enable --now syncthing@pi
# Mac
brew install syncthing && brew services start syncthing
```

Open `http://remndrs-pi.local:8384` (Pi) and `http://localhost:8384` (Mac),
pair the devices, and share `/home/pi/RemndrsNotes` ↔
`~/Library/Mobile Documents/com~apple~CloudDocs/Remndrs`. Syncthing keeps
them identical both ways; iCloud picks the folder up from the Mac as before.

## 7. Decommission the Mac (after verifying)

The bootout commands in steps 3 and 5 already stopped both services. To make
that permanent:

```bash
sudo rm /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
rm ~/Library/LaunchAgents/com.remndrs.plist 2>/dev/null
```

Your Mac's `~/Remndrs` folder and notes stay put — nothing is deleted.

## Updating the Pi later

Pull the latest code and restart the service. The `-t` flag is important: it
gives `sudo` a terminal to prompt for your password on. Without it,
`ssh host 'sudo …'` fails with *"sudo: a terminal is required to read the
password"* — the files update but the service never restarts, so you keep
running the old code (the build stamp in ⚙ Settings won't change).

```bash
ssh -t pi@remndrs-pi.local 'cd ~/Remndrs && git pull && sudo systemctl restart remndrs'
```

Confirm the deploy actually landed — the commit should match the latest one you
pulled:

```bash
ssh pi@remndrs-pi.local 'curl -s localhost:3000/api/version'
```

### Optional: passwordless restart (so the one-liner never stalls)

To let the update command restart the service without a password prompt at all,
add a sudoers rule scoped to just that command (run once on the Pi):

```bash
echo "$USER ALL=(root) NOPASSWD: /bin/systemctl restart remndrs" | \
  sudo tee /etc/sudoers.d/remndrs-restart
sudo chmod 440 /etc/sudoers.d/remndrs-restart
```

Then plain `ssh pi@… 'cd ~/Remndrs && git pull && sudo systemctl restart remndrs'`
works unattended.

## Hosting more sites on the same Pi

The setup above scales to any number of sites — the one cloudflared tunnel
routes them all, with zero open router ports. A few one-time choices make
that painless:

**Before installing anything** (worth doing on day one):

```bash
sudo apt update && sudo apt full-upgrade -y
# security patches install themselves from now on:
sudo apt install -y unattended-upgrades
```

Also give the Pi a **DHCP reservation** in your router's admin page so its
LAN address never changes (the tunnel doesn't care, but SSH and Syncthing do).

**The pattern for every new site** (this is all of it):

1. Run the app as its own user-or-port — keep a port registry in a comment
   at the top of `~/.cloudflared/config.yml`. Remndrs owns **3000**; give the
   next site 3001, then 3002, …
2. One systemd unit per app (copy `remndrs.service`, change the name,
   `WorkingDirectory`, and `ExecStart`).
3. Add the hostname to the tunnel's ingress list and create its DNS route:

```yaml
# ~/.cloudflared/config.yml — ingress rules are matched top-down
tunnel: remndrs
credentials-file: /home/pi/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: remndrs.app          # port registry:
    service: http://localhost:3000 #   3000 remndrs
  - hostname: nextsite.com         #   3001 nextsite
    service: http://localhost:3001
  - service: http_status:404       # catch-all, keep last
```

```bash
# the new domain must be added to your Cloudflare account first (free plan ok)
cloudflared tunnel route dns remndrs nextsite.com
sudo systemctl restart cloudflared
```

That's a new public HTTPS site in ~2 minutes, no certificates to manage,
nothing exposed on your router.

**Two honest cautions for a multi-site Pi:**

- **SD cards wear out.** With several apps writing databases, either boot
  from a USB SSD (Pi 4 supports it natively) or at minimum back up each
  app's data folder somewhere off-Pi on a cron (Remndrs: `data/remndrs.db`
  + the notes folder, which Syncthing already mirrors).
- **One Pi = one failure domain.** If a hobby site gets popular or
  experimental code runs away with the CPU, it can starve the others —
  `htop` is your friend, and `systemd` resource limits (`MemoryMax=`,
  `CPUQuota=`) are the fix.

