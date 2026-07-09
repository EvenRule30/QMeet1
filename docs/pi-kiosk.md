# QMeet Phase 8E — Raspberry Pi Kiosk Startup

This phase keeps laptop development unchanged. The React app still runs normally on the laptop with `npm run dev`, Chrome DevTools, and responsive testing at `1024 × 600`.

The Pi-specific part is only a launcher script that opens Chromium fullscreen/kiosk at the QMeet URL.

## Files to add

```text
scripts/pi-kiosk-start.sh
docs/pi-kiosk.md
```

## Laptop development stays the same

On the laptop, keep using the normal two-terminal workflow.

Backend:

```powershell
cd C:\Users\EvenR\Documents\Work\Chascii\React\QMeet1-1\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd C:\Users\EvenR\Documents\Work\Chascii\React\QMeet1-1
npm run dev -- --host 0.0.0.0
```

Then test in Chrome DevTools responsive mode at:

```text
1024 × 600
```

## Before testing from the Pi

The Pi needs to reach the laptop over the local network.

Find the laptop IPv4 address in PowerShell:

```powershell
ipconfig
```

Look for the IPv4 address on the active Wi-Fi/Ethernet adapter. It will usually look like:

```text
192.168.x.x
```

On the laptop, make sure the frontend `.env.local` points to the laptop backend, not only localhost, when testing from another device:

```env
VITE_QMEET_API_URL=http://YOUR_LAPTOP_IP:8000
```

Restart Vite after changing `.env.local`.

## Run kiosk mode on the Pi

Copy `scripts/pi-kiosk-start.sh` into the repo on the Pi, then run:

```bash
chmod +x scripts/pi-kiosk-start.sh
QMEET_URL=http://YOUR_LAPTOP_IP:5173 ./scripts/pi-kiosk-start.sh
```

Example:

```bash
QMEET_URL=http://192.168.1.50:5173 ./scripts/pi-kiosk-start.sh
```

## Optional scale override

Default scale is `1`. If the UI is too large or too small on the Pi display, test:

```bash
QMEET_SCALE=0.9 QMEET_URL=http://YOUR_LAPTOP_IP:5173 ./scripts/pi-kiosk-start.sh
```

or:

```bash
QMEET_SCALE=1.1 QMEET_URL=http://YOUR_LAPTOP_IP:5173 ./scripts/pi-kiosk-start.sh
```

Use this only if the CSS layout is already correct but Chromium/device scaling looks off.

## Optional: close old Chromium first

If Chromium is already running and kiosk mode behaves strangely:

```bash
QMEET_KILL_CHROMIUM=1 QMEET_URL=http://YOUR_LAPTOP_IP:5173 ./scripts/pi-kiosk-start.sh
```

## Optional autostart later

When the Pi test works manually, you can make it boot straight into QMeet.

Create this file on the Pi:

```bash
mkdir -p ~/.config/autostart
nano ~/.config/autostart/qmeet-kiosk.desktop
```

Example contents:

```ini
[Desktop Entry]
Type=Application
Name=QMeet Kiosk
Exec=/home/pi/QMeet1-1/scripts/pi-kiosk-start.sh
Terminal=false
X-GNOME-Autostart-enabled=true
```

Adjust the `Exec=` path to wherever the repo/script lives on the Pi.

For autostart with a laptop-hosted frontend, edit the script and set the default URL, or put a wrapper script around it:

```bash
#!/usr/bin/env bash
export QMEET_URL=http://YOUR_LAPTOP_IP:5173
exec /home/pi/QMeet1-1/scripts/pi-kiosk-start.sh
```

## What not to change yet

Do not hardcode kiosk behavior into React yet.

Avoid:

```text
- forcing fullscreen from React
- hiding the cursor globally during laptop dev
- blocking right-click/devtools
- hardcoding Pi-only URLs in the app
- removing normal browser testing behavior
```

Keep kiosk behavior in Pi scripts until the tablet software is ready to become a packaged device image.

## Troubleshooting

### Pi cannot open QMeet

Check from the Pi:

```bash
curl http://YOUR_LAPTOP_IP:5173
curl http://YOUR_LAPTOP_IP:8000/health
```

If those fail:

```text
- make sure laptop and Pi are on the same network
- run Vite with --host 0.0.0.0
- run FastAPI with --host 0.0.0.0
- check Windows firewall prompts for Node/Vite and Python/Uvicorn
- confirm the laptop IP did not change
```

### Frontend loads but backend commands fail

Check `.env.local` on the laptop:

```env
VITE_QMEET_API_URL=http://YOUR_LAPTOP_IP:8000
```

Then restart Vite.

### Mic/voice does not work in kiosk

Open QMeet once in normal Chromium on the Pi and allow microphone permission. The script uses a dedicated Chromium profile at:

```text
~/.config/qmeet-kiosk-chromium
```

Permissions should persist there after being accepted.

### Display sleeps

The script tries to disable X11 screen blanking with `xset` if available. If the display still sleeps, adjust Raspberry Pi desktop power/display settings later.
