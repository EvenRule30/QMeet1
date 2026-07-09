#!/usr/bin/env bash
set -euo pipefail

# QMeet Raspberry Pi kiosk launcher
# Usage:
#   QMEET_URL=http://YOUR_LAPTOP_IP:5173 ./scripts/pi-kiosk-start.sh
# Optional:
#   QMEET_SCALE=1 ./scripts/pi-kiosk-start.sh
#   QMEET_KILL_CHROMIUM=1 ./scripts/pi-kiosk-start.sh

QMEET_URL="${QMEET_URL:-http://localhost:5173}"
QMEET_SCALE="${QMEET_SCALE:-1}"
QMEET_USER_DATA_DIR="${QMEET_USER_DATA_DIR:-$HOME/.config/qmeet-kiosk-chromium}"
QMEET_KILL_CHROMIUM="${QMEET_KILL_CHROMIUM:-0}"

find_chromium() {
  if command -v chromium-browser >/dev/null 2>&1; then
    command -v chromium-browser
    return 0
  fi

  if command -v chromium >/dev/null 2>&1; then
    command -v chromium
    return 0
  fi

  if command -v google-chrome >/dev/null 2>&1; then
    command -v google-chrome
    return 0
  fi

  if command -v google-chrome-stable >/dev/null 2>&1; then
    command -v google-chrome-stable
    return 0
  fi

  return 1
}

CHROMIUM_BIN="$(find_chromium || true)"

if [[ -z "$CHROMIUM_BIN" ]]; then
  echo "QMeet kiosk error: Chromium was not found."
  echo "Install Chromium on the Pi, then run this script again."
  exit 1
fi

mkdir -p "$QMEET_USER_DATA_DIR"

if [[ "$QMEET_KILL_CHROMIUM" == "1" ]]; then
  pkill -f chromium || true
  pkill -f chrome || true
fi

# Best-effort screen blanking disable for X11 sessions. Harmless if xset is unavailable.
if command -v xset >/dev/null 2>&1; then
  xset s off || true
  xset -dpms || true
  xset s noblank || true
fi

echo "Starting QMeet kiosk"
echo "Chromium: $CHROMIUM_BIN"
echo "URL:      $QMEET_URL"
echo "Scale:    $QMEET_SCALE"
echo "Profile:  $QMEET_USER_DATA_DIR"

exec "$CHROMIUM_BIN" \
  --kiosk "$QMEET_URL" \
  --start-fullscreen \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --autoplay-policy=no-user-gesture-required \
  --force-device-scale-factor="$QMEET_SCALE" \
  --user-data-dir="$QMEET_USER_DATA_DIR"
