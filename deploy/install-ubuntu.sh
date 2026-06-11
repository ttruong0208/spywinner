#!/usr/bin/env bash
# WinnerSpy VPS setup — Ubuntu 22.04/24.04
# Run as root: bash deploy/install-ubuntu.sh
set -euo pipefail

APP_ROOT="/opt/winnerspy"
REPO="${APP_ROOT}/spywinner"
REPO_URL="${REPO_URL:-https://github.com/ttruong0208/spywinner.git}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install-ubuntu.sh"
  exit 1
fi

echo "==> Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 python3-venv python3-pip git curl nginx certbot python3-certbot-nginx \
  xvfb fonts-liberation libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1

# 2GB RAM VPS: add swap so Chrome does not OOM
if ! swapon --show | grep -q swapfile; then
  if [[ "$(free -m | awk '/^Mem:/{print $2}')" -lt 3500 ]]; then
    echo "==> Adding 2G swap (low RAM VPS)"
    fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
fi

echo "==> Google Chrome"
if ! command -v google-chrome >/dev/null 2>&1 && ! command -v google-chrome-stable >/dev/null 2>&1; then
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list
  apt-get update -qq
  apt-get install -y -qq google-chrome-stable
fi

echo "==> Clone repo"
mkdir -p "$APP_ROOT"
if [[ ! -d "$REPO/.git" ]]; then
  git clone "$REPO_URL" "$REPO"
else
  git -C "$REPO" pull --ff-only || true
fi

echo "==> Python venv"
python3 -m venv "$REPO/venv"
"$REPO/venv/bin/pip" install --upgrade pip -q
"$REPO/venv/bin/pip" install -r "$REPO/requirements-web.txt" -q

echo "==> Directories"
mkdir -p /etc/winnerspy /var/lib/winnerspy "$REPO/jobs" "$REPO/data"
chown -R www-data:www-data "$REPO/jobs" "$REPO/data"
chown -R root:root /var/lib/winnerspy
chmod 755 /var/lib/winnerspy

if [[ ! -f /etc/winnerspy/env ]]; then
  cp "$REPO/deploy/winnerspy.env.example" /etc/winnerspy/env
  chmod 600 /etc/winnerspy/env
  echo "EDIT /etc/winnerspy/env — set SECRET, admin password, Resend key"
fi

chmod +x "$REPO/deploy/start_chrome_debug.sh"

echo "==> systemd"
cp "$REPO/deploy/systemd/winnerspy-chrome.service" /etc/systemd/system/
cp "$REPO/deploy/systemd/winnerspy-web.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable winnerspy-chrome winnerspy-web

echo "==> nginx"
cp "$REPO/deploy/nginx-winnerspy.conf" /etc/nginx/sites-available/winnerspy
ln -sf /etc/nginx/sites-available/winnerspy /etc/nginx/sites-enabled/winnerspy
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> Start services"
systemctl restart winnerspy-chrome
sleep 3
systemctl restart winnerspy-web

echo ""
echo "Done. Next steps:"
echo "  1. nano /etc/winnerspy/env   (SECRET, ADMIN_PASSWORD, RESEND, PAYPAL...)"
echo "  2. systemctl restart winnerspy-web winnerspy-chrome"
echo "  3. Namecheap DNS: A @ and A www -> VPS IP"
echo "  4. certbot --nginx -d winnerspy.app -d www.winnerspy.app"
echo "  5. Open https://winnerspy.app — UI shows Cloud scanning"
echo "  6. Suspend Render service (optional)"
echo ""
echo "Logs: journalctl -u winnerspy-web -f"
echo "       journalctl -u winnerspy-chrome -f"
