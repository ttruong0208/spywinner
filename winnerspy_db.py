#!/usr/bin/env python3
"""SQLite persistence for WinnerSpy Web v5."""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "winnerspy.db"

from winnerspy_plans import PLANS, plan_limits  # noqa: F401


def _parse_opts(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                role TEXT NOT NULL DEFAULT 'user',
                api_key TEXT UNIQUE,
                webhook_url TEXT DEFAULT '',
                cdp_url TEXT DEFAULT 'http://127.0.0.1:9222',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                opts TEXT NOT NULL,
                exit_code INTEGER,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                source TEXT DEFAULT 'web',
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                hour INTEGER NOT NULL DEFAULT 8,
                minute INTEGER NOT NULL DEFAULT 0,
                days TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
                opts TEXT NOT NULL,
                last_run_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
            CREATE TABLE IF NOT EXISTS upgrade_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                transfer_note TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_upgrade_user ON upgrade_requests(user_id);
            """
        )
        _migrate_user_columns(conn)
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        if row["c"] == 0:
            from werkzeug.security import generate_password_hash

            try:
                from winnerspy_auth import admin_bootstrap_password
            except ImportError:
                admin_bootstrap_password = lambda: "admin123"  # noqa: E731

            admin_email = os.environ.get("WINNERSPY_ADMIN_EMAIL", "admin@local").strip()
            admin_pw = admin_bootstrap_password()
            api_key = "ws_" + secrets.token_urlsafe(24)
            conn.execute(
                """
                INSERT INTO users (
                    email, password_hash, plan, role, api_key, created_at,
                    email_verified, verify_token, verify_token_expires
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, NULL, NULL)
                """,
                (
                    admin_email,
                    generate_password_hash(admin_pw),
                    "admin",
                    "admin",
                    api_key,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            print(f"[WinnerSpy] Tao admin: {admin_email}")
            if not os.environ.get("WINNERSPY_ADMIN_PASSWORD", "").strip():
                print(f"[WinnerSpy] Mat khau admin (luu lai): {admin_pw}")


def _migrate_user_columns(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "email_verified" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE users SET email_verified = 1")
    if "verify_token" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN verify_token TEXT")
    if "verify_token_expires" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN verify_token_expires TEXT")


def get_user_by_id(user_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
        return dict(row) if row else None


def get_user_by_api_key(api_key: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
        return dict(row) if row else None


def create_user(email: str, password_hash: str, plan: str = "free") -> int:
    api_key = "ws_" + secrets.token_urlsafe(24)
    code = f"{secrets.randbelow(1000000):06d}"
    expires = (datetime.now() + timedelta(minutes=15)).isoformat(timespec="seconds")
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (
                email, password_hash, plan, role, api_key, created_at,
                email_verified, verify_token, verify_token_expires
            )
            VALUES (?, ?, ?, 'user', ?, ?, 0, ?, ?)
            """,
            (
                email.lower().strip(),
                password_hash,
                plan,
                api_key,
                datetime.now().isoformat(timespec="seconds"),
                code,
                expires,
            ),
        )
        return int(cur.lastrowid)


def get_user_by_verify_token(token: str) -> dict | None:
    if not (token or "").strip():
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE verify_token = ?",
            (token.strip(),),
        ).fetchone()
        return dict(row) if row else None


def mark_email_verified(user_id: int) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE users
            SET email_verified = 1, verify_token = NULL, verify_token_expires = NULL
            WHERE id = ?
            """,
            (user_id,),
        )


def rotate_verify_token(user_id: int) -> str:
    code = f"{secrets.randbelow(1000000):06d}"
    expires = (datetime.now() + timedelta(minutes=15)).isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            """
            UPDATE users SET verify_token = ?, verify_token_expires = ?, email_verified = 0
            WHERE id = ?
            """,
            (code, expires, user_id),
        )
    return code


def verify_token_valid(row: dict) -> bool:
    if not row or not row.get("verify_token"):
        return False
    exp = row.get("verify_token_expires") or ""
    if not exp:
        return True
    try:
        return datetime.fromisoformat(exp) >= datetime.now()
    except ValueError:
        return False


def update_user_settings(user_id: int, webhook_url: str | None = None, cdp_url: str | None = None):
    with connect() as conn:
        if webhook_url is not None:
            conn.execute("UPDATE users SET webhook_url = ? WHERE id = ?", (webhook_url, user_id))
        if cdp_url is not None:
            conn.execute("UPDATE users SET cdp_url = ? WHERE id = ?", (cdp_url, user_id))


def regenerate_api_key(user_id: int) -> str:
    api_key = "ws_" + secrets.token_urlsafe(24)
    with connect() as conn:
        conn.execute("UPDATE users SET api_key = ? WHERE id = ?", (api_key, user_id))
    return api_key


def set_user_plan(user_id: int, plan: str):
    with connect() as conn:
        conn.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))


def count_scans_today(user_id: int) -> int:
    today = date.today().isoformat()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM jobs
            WHERE user_id = ? AND created_at LIKE ?
            """,
            (user_id, today + "%"),
        ).fetchone()
        return int(row["c"])


def insert_job(job_id: str, user_id: int, opts: dict, source: str = "web") -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, user_id, status, opts, created_at, source)
            VALUES (?, ?, 'queued', ?, ?, ?)
            """,
            (job_id, user_id, json.dumps(opts, ensure_ascii=False), datetime.now().isoformat(timespec="seconds"), source),
        )


def update_job_status(job_id: str, status: str, exit_code: int | None = None, error: str | None = None):
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        row = conn.execute("SELECT status, started_at FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return
        started = row["started_at"]
        if status == "running" and not started:
            conn.execute(
                "UPDATE jobs SET status = ?, started_at = ? WHERE id = ?",
                (status, now, job_id),
            )
        elif status in ("done", "failed"):
            conn.execute(
                "UPDATE jobs SET status = ?, exit_code = ?, error = ?, finished_at = ? WHERE id = ?",
                (status, exit_code, error, now, job_id),
            )
        else:
            conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))


def get_job(job_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["opts"] = _parse_opts(d["opts"])
        return d


def list_jobs_for_user(user_id: int, limit: int = 30) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["opts"] = _parse_opts(d["opts"])
            out.append(d)
        return out


def list_all_jobs(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT j.*, u.email FROM jobs j
            JOIN users u ON u.id = j.user_id
            ORDER BY j.created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["opts"] = _parse_opts(d["opts"])
            out.append(d)
        return out


def list_users() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, email, plan, role, created_at, email_verified FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def user_stats(user_id: int) -> dict:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM jobs WHERE user_id = ?", (user_id,)).fetchone()["c"]
        done = conn.execute(
            "SELECT COUNT(*) AS c FROM jobs WHERE user_id = ? AND status = 'done'", (user_id,)
        ).fetchone()["c"]
        return {"total_jobs": total, "done_jobs": done, "scans_today": count_scans_today(user_id)}


# --- Schedules ---

def create_schedule(user_id: int, name: str, hour: int, minute: int, days: str, opts: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO schedules (user_id, name, hour, minute, days, opts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, name, hour, minute, days, json.dumps(opts, ensure_ascii=False)),
        )
        return int(cur.lastrowid)


def list_schedules(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM schedules WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["opts"] = _parse_opts(d["opts"])
            out.append(d)
        return out


def list_enabled_schedules() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM schedules WHERE enabled = 1").fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["opts"] = _parse_opts(d["opts"])
            out.append(d)
        return out


def toggle_schedule(schedule_id: int, user_id: int, enabled: bool):
    with connect() as conn:
        conn.execute(
            "UPDATE schedules SET enabled = ? WHERE id = ? AND user_id = ?",
            (1 if enabled else 0, schedule_id, user_id),
        )


def delete_schedule(schedule_id: int, user_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM schedules WHERE id = ? AND user_id = ?", (schedule_id, user_id))


def touch_schedule_run(schedule_id: int):
    with connect() as conn:
        conn.execute(
            "UPDATE schedules SET last_run_at = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), schedule_id),
        )


def create_upgrade_request(user_id: int, plan: str, transfer_note: str = "") -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO upgrade_requests (user_id, plan, status, transfer_note, created_at)
            VALUES (?, ?, 'pending', ?, ?)
            """,
            (user_id, plan, transfer_note, now),
        )
        return int(cur.lastrowid)


def get_latest_upgrade_request(user_id: int, plan: str, status: str = "pending") -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM upgrade_requests
            WHERE user_id = ? AND plan = ? AND status = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (user_id, plan, status),
        ).fetchone()
        return dict(row) if row else None


def list_pending_upgrade_requests(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT r.*, u.email
            FROM upgrade_requests r
            JOIN users u ON u.id = r.user_id
            WHERE r.status = 'pending'
            ORDER BY r.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_upgrade_request_done(request_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE upgrade_requests SET status = 'done' WHERE id = ?",
            (request_id,),
        )
