"""Auth policy: registration, passwords, rate limits."""
from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from threading import Lock

PASSWORD_MIN_LEN = int(os.environ.get("WINNERSPY_PASSWORD_MIN", "10"))
_RATE_WINDOW_SEC = 900
_RATE_MAX_ATTEMPTS = 12

_rate_lock = Lock()
_rate_buckets: dict[str, list[float]] = defaultdict(list)


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def registration_mode() -> str:
    """open | invite | closed"""
    if _env_truthy("WINNERSPY_ALLOW_REGISTER", "1"):
        return "open"
    invite = os.environ.get("WINNERSPY_INVITE_CODE", "").strip()
    if invite:
        return "invite"
    return "closed"


def registration_allowed() -> bool:
    return registration_mode() != "closed"


def verify_invite_code(code: str) -> bool:
    expected = os.environ.get("WINNERSPY_INVITE_CODE", "").strip()
    if not expected:
        return False
    return secrets_compare(code.strip(), expected)


def secrets_compare(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < PASSWORD_MIN_LEN:
        return False, f"Password must be at least {PASSWORD_MIN_LEN} characters."
    if not re.search(r"[A-Za-z]", password):
        return False, "Password must include at least one letter."
    if not re.search(r"\d", password):
        return False, "Password must include at least one number."
    if password.lower() in {"admin123", "password", "1234567890", "qwerty12345"}:
        return False, "Password is too common — choose a stronger one."
    return True, ""


def check_rate_limit(bucket_key: str) -> tuple[bool, str]:
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate_buckets[bucket_key] if now - t < _RATE_WINDOW_SEC]
        if len(hits) >= _RATE_MAX_ATTEMPTS:
            return False, "Too many attempts. Wait 15 minutes and try again."
        hits.append(now)
        _rate_buckets[bucket_key] = hits
    return True, ""


def client_ip() -> str:
    from flask import request

    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()


def admin_bootstrap_password() -> str:
    """Password for first admin — bắt buộc env mạnh trên production."""
    from winnerspy_security import production_mode

    pw = os.environ.get("WINNERSPY_ADMIN_PASSWORD", "").strip()
    if production_mode():
        if len(pw) < 16:
            raise RuntimeError(
                "Production: set WINNERSPY_ADMIN_PASSWORD (≥16 chars) before starting."
            )
        return pw
    if pw:
        return pw
    return "admin123"


def email_verification_enabled() -> bool:
    """Tắt khi dev: WINNERSPY_SKIP_EMAIL_VERIFY=1"""
    return not _env_truthy("WINNERSPY_SKIP_EMAIL_VERIFY", "0")


def is_user_email_verified(row: dict | None) -> bool:
    if not row:
        return False
    if row.get("role") == "admin" or row.get("plan") == "admin":
        return True
    if not email_verification_enabled():
        return True
    return bool(int(row.get("email_verified") or 0))
