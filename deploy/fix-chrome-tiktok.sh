#!/usr/bin/env bash
# Sửa Chrome VPS: bỏ --headless để TikTok search hoạt động.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/winnerspy/spywinner}"
SERVICE="winnerspy-chrome"

echo "==> Cài Xvfb (Chrome cần display ảo, không headless)"
apt-get update -qq
apt-get install -y -qq xvfb

echo "==> Quyền thực thi script deploy (git pull đôi khi mất +x)"
chmod +x "${APP_DIR}/deploy/"*.sh 2>/dev/null || true

echo "==> Đảm bảo systemd dùng deploy/start_chrome_debug.sh (không headless)"
UNIT="/etc/systemd/system/${SERVICE}.service"
if [[ -f "$UNIT" ]]; then
  if grep -q 'headless' "$UNIT" 2>/dev/null; then
    sed -i 's|--headless=new||g; s|--headless||g' "$UNIT"
    systemctl daemon-reload
    echo "    Đã gỡ --headless khỏi $UNIT"
  fi
  if ! grep -q 'deploy/start_chrome_debug.sh' "$UNIT"; then
    sed -i "s|ExecStart=.*|ExecStart=${APP_DIR}/deploy/start_chrome_debug.sh|" "$UNIT"
    systemctl daemon-reload
    echo "    ExecStart → ${APP_DIR}/deploy/start_chrome_debug.sh"
  fi
fi

CUSTOM="/usr/local/bin/winnerspy-chrome.sh"
if [[ -f "$CUSTOM" ]] && grep -q 'headless' "$CUSTOM"; then
  echo "==> Ghi đè $CUSTOM (bản cũ có --headless)"
  cp "${APP_DIR}/deploy/start_chrome_debug.sh" "$CUSTOM"
  chmod +x "$CUSTOM"
fi

if [[ -f "$UNIT" ]] && ! grep -q 'DISPLAY=:99' "$UNIT"; then
  sed -i '/Environment=APP_DIR/a Environment=DISPLAY=:99' "$UNIT"
  systemctl daemon-reload
fi

echo "==> Dọn lock Chrome cũ"
PROFILE="${CHROME_PROFILE:-/var/lib/winnerspy/chrome_profile}"
pkill -f 'remote-debugging-port' 2>/dev/null || true
sleep 2
rm -f "$PROFILE/SingletonLock" "$PROFILE/SingletonCookie" "$PROFILE/SingletonSocket" 2>/dev/null || true

echo "==> Restart Chrome"
systemctl restart "$SERVICE"
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 3
  if curl -sf "http://127.0.0.1:9222/json/version" >/dev/null; then
    curl -s "http://127.0.0.1:9222/json/version" | head -c 120
    echo ""
    echo "OK — CDP sẵn sàng (sau ${i}x3s). Tạo report mới để kiểm tra TikTok."
    exit 0
  fi
done

echo "WARN — CDP chưa phản hồi sau 30s."
systemctl status "$SERVICE" --no-pager -l | tail -20
journalctl -u "$SERVICE" -n 30 --no-pager
exit 1
