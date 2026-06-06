"""Bảo mật production — admin, CSRF, headers."""
from __future__ import annotations

import os
import secrets

from flask import abort, request, session


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def production_mode() -> bool:
    return _truthy("WINNERSPY_PRODUCTION", "0")


def admin_url_prefix() -> str:
    """Đổi path admin — không dùng /admin công khai. VD: WINNERSPY_ADMIN_PATH=cp-a8f2k9"""
    raw = os.environ.get("WINNERSPY_ADMIN_PATH", "admin").strip().strip("/")
    if not raw or raw in (".", "..") or "/" in raw:
        return "admin"
    return raw[:64]


def admin_ip_allowlist() -> set[str]:
    raw = os.environ.get("WINNERSPY_ADMIN_IPS", "").strip()
    if not raw:
        return set()
    return {x.strip() for x in raw.replace(";", ",").split(",") if x.strip()}


def admin_ip_allowed() -> bool:
    allow = admin_ip_allowlist()
    if not allow:
        return True
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    return ip in allow


def ensure_csrf_token() -> str:
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(24)
    return session["_csrf"]


def validate_csrf() -> bool:
    """True nếu token hợp lệ."""
    expected = session.get("_csrf")
    if not expected or not isinstance(expected, str):
        return False
    got = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
    if not isinstance(got, str):
        got = str(got)
    if not got:
        return False
    try:
        return secrets.compare_digest(got, expected)
    except (TypeError, ValueError):
        return False


def apply_session_cookie_flags(app) -> None:
    if production_mode():
        app.config["SESSION_COOKIE_SECURE"] = _truthy("WINNERSPY_COOKIE_SECURE", "1")
        app.config["SESSION_COOKIE_HTTPONLY"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = os.environ.get("WINNERSPY_COOKIE_SAMESITE", "Lax")


def validate_production_config() -> list[str]:
    """Trả về danh sách lỗi cấu hình (rỗng = OK)."""
    errors: list[str] = []
    if not production_mode():
        return errors
    if not os.environ.get("WINNERSPY_SECRET", "").strip():
        errors.append("Missing WINNERSPY_SECRET (random string, 32+ chars).")
    pw = os.environ.get("WINNERSPY_ADMIN_PASSWORD", "").strip()
    if len(pw) < 16:
        errors.append("WINNERSPY_ADMIN_PASSWORD must be ≥16 chars in production.")
    if pw.lower() in {"admin123", "password", "1234567890123456"}:
        errors.append("Admin password too weak / default.")
    if admin_url_prefix() == "admin":
        errors.append("Change WINNERSPY_ADMIN_PATH (do not use 'admin').")
    if not admin_ip_allowlist():
        errors.append("Set WINNERSPY_ADMIN_IPS (allowed admin IPs).")
    return errors


def security_headers() -> dict[str, str]:
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }
