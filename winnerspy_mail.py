"""Account verification & welcome email — SMTP via env."""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from winnerspy_config import app_base_url


def smtp_configured() -> bool:
    return not smtp_missing_fields()


def smtp_missing_fields() -> list[str]:
    required = {
        "WINNERSPY_SMTP_HOST": os.environ.get("WINNERSPY_SMTP_HOST", ""),
        "WINNERSPY_SMTP_FROM": os.environ.get("WINNERSPY_SMTP_FROM", ""),
        "WINNERSPY_SMTP_USER": os.environ.get("WINNERSPY_SMTP_USER", ""),
        "WINNERSPY_SMTP_PASSWORD": os.environ.get("WINNERSPY_SMTP_PASSWORD", ""),
    }
    return [key for key, val in required.items() if not (val or "").strip()]


def smtp_status_message() -> str:
    missing = smtp_missing_fields()
    if missing:
        return "Missing on Render: " + ", ".join(missing)
    return "SMTP env vars present"


def _smtp_timeout() -> int:
    try:
        return max(5, min(int(os.environ.get("WINNERSPY_SMTP_TIMEOUT", "10")), 30))
    except ValueError:
        return 10


def _smtp_settings() -> dict:
    password = os.environ.get("WINNERSPY_SMTP_PASSWORD", "").strip()
    password = password.replace(" ", "")
    return {
        "host": os.environ.get("WINNERSPY_SMTP_HOST", "").strip(),
        "port": int(os.environ.get("WINNERSPY_SMTP_PORT", "587")),
        "user": os.environ.get("WINNERSPY_SMTP_USER", "").strip(),
        "password": password,
        "from_addr": os.environ.get("WINNERSPY_SMTP_FROM", "").strip(),
        "use_tls": os.environ.get("WINNERSPY_SMTP_TLS", "1").strip().lower() in ("1", "true", "yes"),
        "timeout": _smtp_timeout(),
    }


def _deliver_message(msg: MIMEMultipart, to_email: str) -> bool:
    if not smtp_configured():
        return False
    cfg = _smtp_settings()
    server = None
    try:
        if cfg["use_tls"]:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=cfg["timeout"])
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=cfg["timeout"])
        if cfg["user"] and cfg["password"]:
            server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["from_addr"], [to_email], msg.as_string())
        return True
    except Exception as exc:
        print(f"[WinnerSpy] SMTP error: {exc}")
        return False
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


def build_verify_url(token: str) -> str:
    return f"{app_base_url()}/verify-email?token={token}"


def send_welcome_email(to_email: str, dashboard_url: str) -> bool:
    if not smtp_configured():
        return False

    subject = "Welcome to WinnerSpy — run your first report"
    text = f"""Hi,

Your email is verified. WinnerSpy finds products running Facebook ads for keywords you choose.

First 3 steps (5–15 min):
1. Open your dashboard: {dashboard_url}
2. Use a specific keyword (e.g. magnetic eyelash kit) — avoid broad terms like "cleaning"
3. Preset "Balanced" → Start report → download report.html

— WinnerSpy
"""
    html = f"""<p>Hi,</p>
<p>Your email is verified. <a href="{dashboard_url}">Open your dashboard</a> and run your first report.</p>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _smtp_settings()["from_addr"]
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return _deliver_message(msg, to_email)


def send_verification_code_email(to_email: str, code: str) -> bool:
    """Send 6-digit verification code."""
    if not smtp_configured():
        return False

    verify_url = f"{app_base_url()}/verify-pending"
    subject = f"Your WinnerSpy verification code: {code}"
    text = f"""Hi,

Your WinnerSpy email verification code is:

  {code}

Enter this code on the verification page to activate your account:
{verify_url}

Code expires in 15 minutes. If you did not sign up, ignore this email.

— WinnerSpy
"""
    html = f"""<p>Hi,</p>
<p>Your WinnerSpy verification code is:</p>
<p style="font-size:28px;font-weight:800;letter-spacing:0.25em;margin:16px 0">{code}</p>
<p>Enter this code on the <a href="{verify_url}">verification page</a> to start using WinnerSpy.</p>
<p><small>Expires in 15 minutes.</small></p>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _smtp_settings()["from_addr"]
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return _deliver_message(msg, to_email)


def send_verification_email(to_email: str, verify_url: str) -> bool:
    """Legacy link-based verify — kept for backwards compatibility."""
    code = (verify_url or "").split("code=")[-1].split("&")[0] if "code=" in (verify_url or "") else ""
    if code.isdigit() and len(code) == 6:
        return send_verification_code_email(to_email, code)
    if not smtp_configured():
        return False

    subject = "Verify your email — WinnerSpy"
    text = f"Hi,\n\nConfirm your email:\n{verify_url}\n\n— WinnerSpy\n"
    html = f'<p>Hi,</p><p><a href="{verify_url}">Verify email</a></p>'

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _smtp_settings()["from_addr"]
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return _deliver_message(msg, to_email)
