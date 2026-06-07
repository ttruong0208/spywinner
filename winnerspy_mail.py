"""Account verification & welcome email — SMTP via env."""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


from winnerspy_config import app_base_url


def smtp_configured() -> bool:
    return bool(
        os.environ.get("WINNERSPY_SMTP_HOST", "").strip()
        and os.environ.get("WINNERSPY_SMTP_FROM", "").strip()
    )


def build_verify_url(token: str) -> str:
    return f"{app_base_url()}/verify-email?token={token}"


def send_welcome_email(to_email: str, dashboard_url: str) -> bool:
    if not smtp_configured():
        return False

    host = os.environ.get("WINNERSPY_SMTP_HOST", "").strip()
    port = int(os.environ.get("WINNERSPY_SMTP_PORT", "587"))
    user = os.environ.get("WINNERSPY_SMTP_USER", "").strip()
    password = os.environ.get("WINNERSPY_SMTP_PASSWORD", "").strip()
    from_addr = os.environ.get("WINNERSPY_SMTP_FROM", "").strip()
    use_tls = os.environ.get("WINNERSPY_SMTP_TLS", "1").strip().lower() in ("1", "true", "yes")

    subject = "Welcome to WinnerSpy — run your first report"
    text = f"""Hi,

Your email is verified. WinnerSpy finds products running Facebook ads for keywords you choose.

First 3 steps (5–15 min):
1. Open your dashboard: {dashboard_url}
2. Use a specific keyword (e.g. magnetic eyelash kit) — avoid broad terms like "cleaning"
3. Preset "Balanced" → Start report → download report.html

Notes:
• Source: Facebook Ads Library (your keywords), not a global ad database like AdSpy.
• "Strict winner" may return 0 matches on broad keywords — scored.csv & ads library still available.

Need help? Reply to this email or contact support on the site.

— WinnerSpy
"""
    html = f"""<p>Hi,</p>
<p>Your email is verified. Create your <strong>first product report</strong>:</p>
<ol>
<li><a href="{dashboard_url}">Open dashboard</a></li>
<li>Specific keyword (e.g. <em>portable blender</em>) — preset <strong>Balanced</strong></li>
<li><strong>Start report</strong> → download <code>report.html</code></li>
</ol>
<p><small>WinnerSpy uses Facebook Ads Library for your keywords — transparent limits, fair pricing.</small></p>
<p><a href="{dashboard_url}" style="display:inline-block;padding:12px 24px;background:#4f46e5;color:#fff;text-decoration:none;border-radius:8px;font-weight:700">Open WinnerSpy</a></p>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        if user and password:
            server.login(user, password)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[WinnerSpy] Welcome mail error: {e}")
        return False


def send_verification_code_email(to_email: str, code: str) -> bool:
    """Send 6-digit verification code."""
    if not smtp_configured():
        return False

    host = os.environ.get("WINNERSPY_SMTP_HOST", "").strip()
    port = int(os.environ.get("WINNERSPY_SMTP_PORT", "587"))
    user = os.environ.get("WINNERSPY_SMTP_USER", "").strip()
    password = os.environ.get("WINNERSPY_SMTP_PASSWORD", "").strip()
    from_addr = os.environ.get("WINNERSPY_SMTP_FROM", "").strip()
    use_tls = os.environ.get("WINNERSPY_SMTP_TLS", "1").strip().lower() in ("1", "true", "yes")
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
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        if user and password:
            server.login(user, password)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[WinnerSpy] SMTP error: {e}")
        return False


def send_verification_email(to_email: str, verify_url: str) -> bool:
    """Legacy link-based verify — kept for backwards compatibility."""
    code = (verify_url or "").split("code=")[-1].split("&")[0] if "code=" in (verify_url or "") else ""
    if code.isdigit() and len(code) == 6:
        return send_verification_code_email(to_email, code)
    if not smtp_configured():
        return False

    host = os.environ.get("WINNERSPY_SMTP_HOST", "").strip()
    port = int(os.environ.get("WINNERSPY_SMTP_PORT", "587"))
    user = os.environ.get("WINNERSPY_SMTP_USER", "").strip()
    password = os.environ.get("WINNERSPY_SMTP_PASSWORD", "").strip()
    from_addr = os.environ.get("WINNERSPY_SMTP_FROM", "").strip()
    use_tls = os.environ.get("WINNERSPY_SMTP_TLS", "1").strip().lower() in ("1", "true", "yes")

    subject = "Verify your email — WinnerSpy"
    text = f"""Hi,

Thanks for signing up for WinnerSpy. Click the link below to activate your account:

{verify_url}

Link expires in 48 hours. If you did not sign up, ignore this email.

— WinnerSpy
"""
    html = f"""<p>Hi,</p>
<p>Thanks for signing up for <strong>WinnerSpy</strong>. Confirm your email:</p>
<p><a href="{verify_url}" style="display:inline-block;padding:12px 24px;background:#2563eb;color:#fff;text-decoration:none;border-radius:8px;font-weight:700">Verify email</a></p>
<p>Or copy: <a href="{verify_url}">{verify_url}</a></p>
<p><small>Expires in 48 hours.</small></p>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        if user and password:
            server.login(user, password)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[WinnerSpy] SMTP error: {e}")
        return False
