"""Account verification & welcome email — Resend (Render free) or SMTP (local)."""
from __future__ import annotations

import json
import os
import smtplib
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from winnerspy_config import app_base_url


def resend_configured() -> bool:
    return bool(os.environ.get("WINNERSPY_RESEND_API_KEY", "").strip())


def resend_from_address() -> str:
    return os.environ.get(
        "WINNERSPY_RESEND_FROM",
        "WinnerSpy <onboarding@resend.dev>",
    ).strip()


def smtp_configured() -> bool:
    return not smtp_missing_fields()


def email_configured() -> bool:
    """True when Resend API or SMTP is ready."""
    return resend_configured() or smtp_configured()


def smtp_missing_fields() -> list[str]:
    required = {
        "WINNERSPY_SMTP_HOST": os.environ.get("WINNERSPY_SMTP_HOST", ""),
        "WINNERSPY_SMTP_FROM": os.environ.get("WINNERSPY_SMTP_FROM", ""),
        "WINNERSPY_SMTP_USER": os.environ.get("WINNERSPY_SMTP_USER", ""),
        "WINNERSPY_SMTP_PASSWORD": os.environ.get("WINNERSPY_SMTP_PASSWORD", ""),
    }
    return [key for key, val in required.items() if not (val or "").strip()]


def email_status_message() -> str:
    if resend_configured():
        return "Resend API configured"
    missing = smtp_missing_fields()
    if missing:
        return "Missing: " + ", ".join(missing)
    return "SMTP env vars present"


def _smtp_timeout() -> int:
    try:
        return max(5, min(int(os.environ.get("WINNERSPY_SMTP_TIMEOUT", "10")), 30))
    except ValueError:
        return 10


def _smtp_settings() -> dict:
    password = os.environ.get("WINNERSPY_SMTP_PASSWORD", "").strip().replace(" ", "")
    return {
        "host": os.environ.get("WINNERSPY_SMTP_HOST", "").strip(),
        "port": int(os.environ.get("WINNERSPY_SMTP_PORT", "587")),
        "user": os.environ.get("WINNERSPY_SMTP_USER", "").strip(),
        "password": password,
        "from_addr": os.environ.get("WINNERSPY_SMTP_FROM", "").strip(),
        "use_tls": os.environ.get("WINNERSPY_SMTP_TLS", "1").strip().lower() in ("1", "true", "yes"),
        "timeout": _smtp_timeout(),
    }


def _resend_send(to_email: str, subject: str, html: str, text: str = "") -> bool:
    api_key = os.environ.get("WINNERSPY_RESEND_API_KEY", "").strip()
    if not api_key:
        return False
    payload = {
        "from": resend_from_address(),
        "to": [to_email.strip().lower()],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"[WinnerSpy] Resend HTTP {exc.code}: {detail}")
        return False
    except Exception as exc:
        print(f"[WinnerSpy] Resend error: {exc}")
        return False


def _deliver_smtp(msg: MIMEMultipart, to_email: str) -> bool:
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
    if not email_configured():
        return False

    subject = "Welcome to WinnerSpy — run your first report"
    text = f"""Hi,

Your email is verified. Open your dashboard: {dashboard_url}

— WinnerSpy
"""
    html = f"""<p>Hi,</p>
<p>Your email is verified. <a href="{dashboard_url}">Open your dashboard</a> and run your first report.</p>"""

    if resend_configured():
        return _resend_send(to_email, subject, html, text)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _smtp_settings()["from_addr"]
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return _deliver_smtp(msg, to_email)


def send_verification_code_email(to_email: str, code: str) -> bool:
    """Send 6-digit verification code via Resend (production) or SMTP (local)."""
    if not email_configured():
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

    if resend_configured():
        return _resend_send(to_email, subject, html, text)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _smtp_settings()["from_addr"]
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return _deliver_smtp(msg, to_email)


def send_verification_email(to_email: str, verify_url: str) -> bool:
    """Legacy link-based verify."""
    code = (verify_url or "").split("code=")[-1].split("&")[0] if "code=" in (verify_url or "") else ""
    if code.isdigit() and len(code) == 6:
        return send_verification_code_email(to_email, code)
    if not email_configured():
        return False

    subject = "Verify your email — WinnerSpy"
    text = f"Hi,\n\nConfirm your email:\n{verify_url}\n\n— WinnerSpy\n"
    html = f'<p>Hi,</p><p><a href="{verify_url}">Verify email</a></p>'

    if resend_configured():
        return _resend_send(to_email, subject, html, text)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _smtp_settings()["from_addr"]
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return _deliver_smtp(msg, to_email)
