# QMeet Raspberry Pi Kiosk Guide

QMeet can run as a fullscreen Chromium kiosk on a Raspberry Pi while the React frontend and FastAPI backend are hosted either on the Pi itself or on another machine on the same network.

Normal laptop development does not require any kiosk configuration. The Pi-specific behavior is isolated in:

```text
scripts/pi-kiosk-start.sh
docs/pi-kiosk-autostart-example.desktop
```

## Recommended development layout

For active development, the simplest setup is usually:

```text
Development machine
|- FastAPI backend :8000
`- Vite frontend   :5173

Raspberry Pi
`- Chromium kiosk -> http://DEVELOPMENT_MACHINE_IP:5173
```

The Pi browser loads the frontend from the development machine. The frontend must then be configured to call the development machine's backend address, not `localhost`.

## 1. Find the host machine LAN address

On Windows:

```powershell
ipconfig
```

On Linux/macOS:

```bash
ip addr
```

or:

```bash
ifconfig
```

Use the LAN IPv4 address reachable from the Pi, for example:

```text
192.168.1.50
```

## 2. Configure the frontend for LAN access

On the machine running QMeet, set `.env.local`:

```env
VITE_QMEET_API_URL=http://192.168.1.50:8000
```

Replace the example IP with the host machine's actual address.

Restart Vite after changing `.env.local`:

```bash
npm run dev -- --host 0.0.0.0
```

The `--host 0.0.0.0` flag is important because the Pi must be able to reach Vite over the LAN.

Run the backend so it is also reachable on the network:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 3. Verify connectivity from the Pi

Before using kiosk mode, open Chromium normally on the Pi and test:

```text
http://192.168.1.50:5173
```

Also verify the backend if needed:

```text
http://192.168.1.50:8000/health
```

Do not debug the kiosk script until these URLs work in an ordinary Pi browser tab.

If they do not load, check:

- both devices are on the same reachable network;
- Vite and FastAPI are listening on `0.0.0.0`;
- the host firewall allows ports `5173` and `8000`;
- `.env.local` uses the host LAN IP, not `localhost`;
- the IP address has not changed since the previous session.

## 4. Launch the kiosk

On the Pi, from the QMeet repository:

```bash
chmod +x scripts/pi-kiosk-start.sh
QMEET_URL=http://192.168.1.50:5173 ./scripts/pi-kiosk-start.sh
```

The launcher searches for these browser executables in order:

```text
chromium-browser
chromium
google-chrome
google-chrome-stable
```

If none are installed, the script exits with an explanatory error.

## Launcher options

`pi-kiosk-start.sh` supports these environment variables:

### `QMEET_URL`

Frontend URL to open.

Default:

```text
http://localhost:5173
```

Remote-development example:

```bash
QMEET_URL=http://192.168.1.50:5173 ./scripts/pi-kiosk-start.sh
```

### `QMEET_SCALE`

Chromium device scale factor.

Default:

```text
1
```

Example:

```bash
QMEET_SCALE=1.1 QMEET_URL=http://192.168.1.50:5173 ./scripts/pi-kiosk-start.sh
```

Use this only if the 1024x600 layout needs display-specific scaling.

### `QMEET_USER_DATA_DIR`

Persistent Chromium profile directory.

Default:

```text
~/.config/qmeet-kiosk-chromium
```

This profile is important for microphone/camera permission persistence and other kiosk browser state.

### `QMEET_KILL_CHROMIUM`

Set to `1` to kill existing Chromium/Chrome processes before launch.

Default:

```text
0
```

Example:

```bash
QMEET_KILL_CHROMIUM=1 QMEET_URL=http://192.168.1.50:5173 ./scripts/pi-kiosk-start.sh
```

Use it carefully if the Pi is running other Chromium sessions.

## Microphone and camera permissions

QMeet uses browser APIs for voice input and camera capture. Chromium may require permission the first time each is used.

Because the kiosk launcher uses a persistent user-data directory, permissions can survive subsequent kiosk launches.

A practical setup is:

1. launch QMeet once in normal Chromium using the same profile if needed;
2. allow microphone and camera access;
3. close Chromium;
4. start the kiosk launcher again.

If permissions become corrupted or you deliberately want a clean kiosk profile, stop Chromium and remove or rename:

```text
~/.config/qmeet-kiosk-chromium
```

You will need to grant browser permissions again afterward.

## Autostart on login

A template exists at:

```text
docs/pi-kiosk-autostart-example.desktop
```

Copy it to the Pi autostart directory:

```bash
mkdir -p ~/.config/autostart
cp docs/pi-kiosk-autostart-example.desktop ~/.config/autostart/qmeet-kiosk.desktop
```

Then edit the copied file so both the repository path and `QMEET_URL` match the Pi installation.

A typical desktop entry is:

```ini
[Desktop Entry]
Type=Application
Name=QMeet Kiosk
Exec=/usr/bin/env QMEET_URL=http://192.168.1.50:5173 /home/pi/QMeet1/scripts/pi-kiosk-start.sh
Terminal=false
X-GNOME-Autostart-enabled=true
```

Do not assume `/home/pi/QMeet1` is correct on every machine. Use the actual clone location.

If network availability is slow at login, the desktop environment may start Chromium before the host is reachable. In that case, use the Pi's normal desktop autostart/delay mechanism or a systemd user service rather than adding retry logic to the QMeet application itself.

## Running everything on the Pi

QMeet can also be run with both Vite/FastAPI on the Pi. In that case:

```env
VITE_QMEET_API_URL=http://localhost:8000
```

and the kiosk launcher can use its default URL:

```bash
./scripts/pi-kiosk-start.sh
```

For a production-like Pi deployment, serving a built frontend is preferable to leaving the Vite development server running indefinitely. The current repository launcher is intentionally a prototype/development kiosk helper rather than a full deployment system.

## Screen blanking

The launcher makes a best-effort attempt to disable X11 screen blanking with `xset` when available. This is harmless when `xset` is unavailable, but it may not control blanking under every desktop/Wayland configuration.

If the display still sleeps, configure the Pi desktop/power-management settings directly.

## Kiosk troubleshooting

### Chromium was not found

Install Chromium or Chrome and verify one of these commands resolves:

```bash
command -v chromium-browser
command -v chromium
command -v google-chrome
command -v google-chrome-stable
```

### QMeet opens but backend actions fail

The Pi is only displaying the frontend. Check the frontend build/runtime API address:

```env
VITE_QMEET_API_URL=http://HOST_IP:8000
```

Then verify `http://HOST_IP:8000/health` from the Pi.

### Voice or camera works on the laptop but not the Pi

Check site permissions in the kiosk Chromium profile. Browser media permissions can differ by profile and origin.

Also remember that changing from one host IP to another changes the web origin from Chromium's perspective and may require new permissions.

### The UI scale is wrong

Try a small `QMEET_SCALE` adjustment rather than changing application CSS only for one display:

```bash
QMEET_SCALE=0.9 QMEET_URL=http://HOST_IP:5173 ./scripts/pi-kiosk-start.sh
```

or:

```bash
QMEET_SCALE=1.1 QMEET_URL=http://HOST_IP:5173 ./scripts/pi-kiosk-start.sh
```

### The kiosk launches an old/broken browser session

Try:

```bash
QMEET_KILL_CHROMIUM=1 QMEET_URL=http://HOST_IP:5173 ./scripts/pi-kiosk-start.sh
```

If the problem is profile-specific, stop Chromium and reset `QMEET_USER_DATA_DIR` only after understanding that stored permissions/settings will be lost.

## Security note

The current kiosk setup is for prototype LAN use. Do not expose the FastAPI development server or Vite development server directly to the public internet. Tighten backend CORS, authentication, secret handling, and deployment configuration before treating QMeet as an internet-facing service.
