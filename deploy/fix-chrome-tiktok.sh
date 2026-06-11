#!/usr/bin/env bash
# Sửa Chrome VPS: bỏ --headless để TikTok search hoạt động.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/winnerspy/spywinner}"
SERVICE="winnerspy-chrome"

echo "==> Cài Xvfb (Chrome cần display ảo, không headless)"
apt-get update -qq
apt-get install -y -qq xvfb

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

echo "==> Restart Chrome"
systemctl restart "$SERVICE"
sleep 3
if curl -sf "http://127.0.0.1:9222/json/version" | head -c 80; then
  echo ""
  echo "OK — CDP sẵn sàng. Tạo report mới để kiểm tra TikTok."
else
  echo "WARN — CDP chưa phản hồi. Xem: journalctl -u $SERVICE -n 40 --no-pager"
  exit 1
fi
