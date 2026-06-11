# Deploy WinnerSpy lên VPS Ubuntu

Web + Chrome quét Facebook trên **một VPS**. Khách vào `https://winnerspy.app` — không cần cài gì.

## Yêu cầu

- Ubuntu 22.04 hoặc 24.04
- Tối thiểu **2GB RAM** (nên 4GB); script tự thêm swap nếu RAM thấp
- Domain trỏ **A record** `@` và `www` → IP VPS

## Bước 1 — SSH vào VPS

Panel nhà cung cấp → copy **IP**, **user** (thường `root`), **password**.

Windows PowerShell:

```powershell
ssh root@YOUR_VPS_IP
```

## Bước 2 — Cài một lệnh

```bash
apt update && apt install -y git
git clone https://github.com/ttruong0208/spywinner.git /opt/winnerspy/spywinner
cd /opt/winnerspy/spywinner
bash deploy/install-ubuntu.sh
```

## Bước 3 — Sửa env (copy từ Render)

```bash
nano /etc/winnerspy/env
```

Bắt buộc đổi:

- `WINNERSPY_SECRET` — chuỗi random ≥32 ký tự
- `WINNERSPY_ADMIN_PASSWORD` — mật khẩu admin
- `WINNERSPY_RESEND_API_KEY` — key Resend
- `WINNERSPY_PAYPAL_ME` — PayPal.me

Giữ sẵn:

```env
WINNERSPY_PRODUCTION=1
WINNERSPY_SAAS_MODE=1
WINNERSPY_APP_URL=https://winnerspy.app
WINNERSPY_CDP_URL=http://127.0.0.1:9222
```

Lưu: `Ctrl+O` Enter, thoát: `Ctrl+X`

```bash
systemctl restart winnerspy-web winnerspy-chrome
```

## Bước 4 — DNS (Namecheap)

| Type | Host | Value |
|------|------|-------|
| A | `@` | IP VPS |
| A | `www` | IP VPS |

Xóa CNAME trỏ Render nếu còn.

Đợi 5–30 phút.

## Bước 5 — HTTPS

```bash
certbot --nginx -d winnerspy.app -d www.winnerspy.app
```

## Bước 6 — Render

Render Dashboard → service `spywinner` → **Suspend** (không xóa repo).

## Kiểm tra

```bash
curl -s http://127.0.0.1:9222/json/version | head
systemctl status winnerspy-web winnerspy-chrome
journalctl -u winnerspy-web -n 30 --no-pager
```

Mở https://winnerspy.app → đăng ký → dashboard hiện **Cloud scanning** → tạo report.

## Cập nhật code sau này

```bash
cd /opt/winnerspy/spywinner
git pull
/opt/winnerspy/spywinner/venv/bin/pip install -r requirements-web.txt -q
systemctl restart winnerspy-web winnerspy-chrome
```

## Lỗi thường gặp

| Lỗi | Cách xử lý |
|-----|------------|
| Quét báo Chrome not ready | `systemctl restart winnerspy-chrome` |
| Hết RAM | Nâng gói 4GB hoặc reboot VPS |
| Email không gửi | Kiểm tra Resend key trong `/etc/winnerspy/env` |
| FB chặn / captcha | Cần login Facebook trong Chrome VPS (hỏi support nếu cần VNC) |
| TikTok = unavailable | Chrome **không** được chạy `--headless`. Chạy `bash deploy/fix-chrome-tiktok.sh` rồi `systemctl restart winnerspy-chrome` |
| GTrend = no data | Bình thường với tên SP quá dài; code đã rút gọn keyword. Thử lại report sau vài phút (Google rate limit) |
