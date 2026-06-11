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

```bash
ssh pi@remndrs-pi.local 'cd ~/Remndrs && git pull && sudo systemctl restart remndrs'
```
