#!/usr/bin/env bash
# Chrome remote debugging for WinnerSpy (Linux VPS). Runs in foreground for systemd.
set -euo pipefail

PORT="${CHROME_DEBUG_PORT:-9222}"
PROFILE="${CHROME_PROFILE:-/var/lib/winnerspy/chrome_profile}"

mkdir -p "$PROFILE"

CHROME=""
for bin in google-chrome google-chrome-stable chromium-browser chromium; do
  if command -v "$bin" >/dev/null 2>&1; then
    CHROME="$bin"
    break
  fi
done

if [[ -z "$CHROME" ]]; then
  echo "Install Chrome: apt install -y google-chrome-stable"
  exit 1
fi

export DISPLAY="${DISPLAY:-:99}"
if ! pgrep -x Xvfb >/dev/null 2>&1; then
  if command -v Xvfb >/dev/null 2>&1; then
    Xvfb :99 -screen 0 1280x720x24 -nolisten tcp &
    sleep 1
  fi
fi

# Không dùng --headless: TikTok chặn headless → báo cáo "unavailable".
exec "$CHROME" \
  --remote-debugging-port="$PORT" \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$PROFILE" \
  --no-first-run \
  --disable-session-crashed-bubble \
  --disable-dev-shm-usage \
  --disable-blink-features=AutomationControlled \
  --window-size=1280,720 \
  --no-sandbox \
  "https://www.facebook.com/ads/library/"
