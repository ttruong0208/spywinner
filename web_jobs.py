#!/usr/bin/env python3
"""Job runner for WinnerSpy Web v5 — per-user folders + DB sync."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

import winnerspy_db as db
from winnerspy_config import saas_mode, server_cdp_url
from winnerspy_plans import plan_limits, resolve_keywords

BASE_DIR = Path(__file__).resolve().parent
JOBS_ROOT = BASE_DIR / "jobs"
R_SCRIPT = BASE_DIR / "r.py"

PRESETS = ("cleaning_us", "cleaning_vn", "home_gadget_us")
PRESET_LABELS = {
    "cleaning_us": "Cleaning products (US)",
    "cleaning_vn": "Cleaning products (Vietnam)",
    "home_gadget_us": "Home gadgets (US)",
}


def ensure_dirs():
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)


def new_job_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]


def job_path(user_id: int, job_id: str) -> Path:
    return JOBS_ROOT / str(user_id) / job_id


def job_meta_path(user_id: int, job_id: str) -> Path:
    return job_path(user_id, job_id) / "job.json"


def load_job_meta(user_id: int, job_id: str) -> dict | None:
    p = job_meta_path(user_id, job_id)
    if not p.is_file():
        j = db.get_job(job_id)
        if j and j["user_id"] == user_id:
            return {
                "id": job_id,
                "user_id": user_id,
                "status": j["status"],
                "opts": j["opts"],
                "created_at": j["created_at"],
            }
        return None
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def save_job_meta(meta: dict):
    uid = meta["user_id"]
    jid = meta["id"]
    d = job_path(uid, jid)
    d.mkdir(parents=True, exist_ok=True)
    with job_meta_path(uid, jid).open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def tail_log(user_id: int, job_id: str, lines: int = 80) -> str:
    log_file = job_path(user_id, job_id) / "log.txt"
    if not log_file.is_file():
        return ""
    text = log_file.read_text(encoding="utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])


def build_r_command(user_id: int, job_id: str, opts: dict) -> list[str]:
    d = job_path(user_id, job_id)
    d.mkdir(parents=True, exist_ok=True)

    label_filter = opts.get("label_filter") or ""
    cmd = [
        sys.executable,
        str(R_SCRIPT),
        "--country",
        opts.get("country", "US"),
        "--scroll",
        str(opts.get("scroll", 8)),
        "--top",
        str(opts.get("top", 20)),
        "--raw-out",
        str(d / "raw_ads.csv"),
        "--winners-out",
        str(d / "winner_products.csv"),
        "--scored-out",
        str(d / "scored_products.csv"),
        "--links-out",
        str(d / "search_links.txt"),
        "--final-out",
        str(d / "final_research_results.csv"),
        "--report",
        str(d / "report.html"),
    ]

    if opts.get("cdp"):
        cmd.extend(["--cdp", opts["cdp"]])

    keywords = (opts.get("keywords") or "").strip()
    preset = (opts.get("preset") or "").strip()
    if keywords:
        kw_file = d / "keywords.txt"
        kw_file.write_text(keywords.replace(",", "\n"), encoding="utf-8")
        cmd.extend(["--keywords", str(kw_file)])
    elif preset:
        cmd.extend(["--preset", preset])
    else:
        cmd.extend(["--preset", "cleaning_us"])

    if opts.get("tiktok"):
        cmd.append("--tiktok")
        cmd.extend(["--tiktok-limit", str(opts.get("tiktok_limit", 15))])

    if opts.get("google_trends"):
        cmd.append("--google-trends")
        cmd.extend(["--gt-limit", str(opts.get("gt_limit", 10))])

    fp = (opts.get("filter_preset") or "balanced").strip()
    cmd.extend(["--filter-preset", fp])

    def _extend_filter_cmd(command: list):
        media = (opts.get("filter_media") or "any").strip()
        if media in ("video", "image"):
            command.extend(["--filter-media", media])
        tech = (opts.get("filter_tech") or "any").strip()
        if tech == "shopify":
            command.extend(["--filter-tech", "shopify"])
        for key, flag in (
            ("filter_min_ads", "--filter-min-ads"),
            ("filter_min_days", "--filter-min-days"),
            ("filter_max_days", "--filter-max-days"),
        ):
            raw = (opts.get(key) or "").strip()
            if raw.isdigit() and int(raw) > 0:
                command.extend([flag, raw])
        sort_by = (opts.get("filter_sort") or "").strip()
        if sort_by:
            command.extend(["--filter-sort", sort_by])
        if opts.get("filter_product_only"):
            command.append("--filter-product-only")
        if opts.get("filter_no_marketplace"):
            command.append("--filter-no-marketplace")

    _extend_filter_cmd(cmd)

    if opts.get("from_raw"):
        cmd = [
            sys.executable,
            str(R_SCRIPT),
            "--from-raw",
            str(d / "raw_ads.csv"),
            "--winners-out",
            str(d / "winner_products.csv"),
            "--scored-out",
            str(d / "scored_products.csv"),
            "--final-out",
            str(d / "final_research_results.csv"),
            "--report",
            str(d / "report.html"),
        ]
        if opts.get("tiktok"):
            cmd.append("--tiktok")
            cmd.extend(["--tiktok-limit", str(opts.get("tiktok_limit", 15))])
        if opts.get("google_trends"):
            cmd.append("--google-trends")
            cmd.extend(["--gt-limit", str(opts.get("gt_limit", 10))])
        cmd.extend(["--filter-preset", fp])
        _extend_filter_cmd(cmd)

    return cmd


def _fire_webhook(user_id: int, job_id: str, status: str):
    user = db.get_user_by_id(user_id)
    url = (user or {}).get("webhook_url", "").strip()
    if not url:
        return
    payload = json.dumps({"job_id": job_id, "status": status, "user_id": user_id}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception:
        pass


def _run_subprocess(user_id: int, job_id: str, cmd: list[str]):
    log_file = job_path(user_id, job_id) / "log.txt"
    db.update_job_status(job_id, "running")
    meta = load_job_meta(user_id, job_id) or {"id": job_id, "user_id": user_id, "opts": {}}
    meta["status"] = "running"
    meta["started_at"] = datetime.now().isoformat(timespec="seconds")
    save_job_meta(meta)

    try:
        with log_file.open("w", encoding="utf-8") as log:
            log.write("CMD: " + " ".join(cmd) + "\n\n")
            log.flush()
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
            proc = subprocess.run(
                cmd,
                cwd=str(BASE_DIR),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        status = "done" if proc.returncode == 0 else "failed"
        job_dir = job_path(user_id, job_id)
        raw_csv = job_dir / "raw_ads.csv"
        winners_csv = job_dir / "winner_products.csv"
        if status == "failed" and raw_csv.is_file() and raw_csv.stat().st_size > 200:
            status = "done"
            meta["warning"] = (
                "Facebook scan completed; TikTok step may have failed — see CSV/HTML report."
            )
        db.update_job_status(job_id, status, exit_code=proc.returncode)
        meta = load_job_meta(user_id, job_id) or meta
        meta["status"] = status
        meta["exit_code"] = proc.returncode
        meta["finished_at"] = datetime.now().isoformat(timespec="seconds")
        scored_csv = job_dir / "scored_products.csv"
        if status == "done" and not winners_csv.is_file() and not scored_csv.is_file():
            meta["warning"] = meta.get("warning") or "Missing product data (scored/winners)"
        elif status == "done" and scored_csv.is_file() and (
            not winners_csv.is_file() or winners_csv.stat().st_size < 80
        ):
            meta["warning"] = meta.get("warning") or (
                "0 products match preset filter — see scored_products.csv and Ads Library"
            )
        save_job_meta(meta)
        _fire_webhook(user_id, job_id, status)
    except Exception as e:
        db.update_job_status(job_id, "failed", error=str(e))
        meta = load_job_meta(user_id, job_id) or meta
        meta["status"] = "failed"
        meta["error"] = str(e)
        save_job_meta(meta)
        _fire_webhook(user_id, job_id, "failed")


def can_start_scan(user_id: int) -> tuple[bool, str]:
    user = db.get_user_by_id(user_id)
    if not user:
        return False, "User not found"
    limits = db.plan_limits(user["plan"])
    today = db.count_scans_today(user_id)
    if today >= limits["scans_per_day"]:
        return False, (
            f"Daily scan limit reached ({limits['scans_per_day']}). Upgrade to Pro/VIP or try tomorrow."
        )
    return True, ""


def normalize_opts_for_user(user_id: int, opts: dict) -> dict:
    user = db.get_user_by_id(user_id)
    plan = user["plan"] if user else "free"
    limits = plan_limits(plan)
    o = dict(opts)
    if not limits["api"] and o.get("source") == "api":
        raise ValueError("Free plan cannot use the API. Upgrade to Pro.")
    o["scroll"] = min(int(o.get("scroll", 8)), limits["scroll_max"])
    o["top"] = min(int(o.get("top", 20)), limits["top_max"])

    if not limits.get("tiktok"):
        o["tiktok"] = False
        o["tiktok_limit"] = 0
    elif o.get("tiktok"):
        o["tiktok_limit"] = min(int(o.get("tiktok_limit", 8)), limits["tiktok_max"])
    else:
        o["tiktok_limit"] = 0

    if not limits.get("google_trends"):
        o["google_trends"] = False
        o["gt_limit"] = 0
    elif o.get("google_trends"):
        cap = limits["gt_max"]
        o["gt_limit"] = cap if cap >= 999 else min(int(o.get("gt_limit", 10)), cap)
    else:
        o["gt_limit"] = 0

    kw_text, _kw_n = resolve_keywords(o, limits)
    o["keywords"] = kw_text
    o["preset"] = ""

    if saas_mode():
        o["cdp"] = server_cdp_url()
    elif user and not o.get("cdp"):
        o["cdp"] = user.get("cdp_url") or "http://127.0.0.1:9222"
    return o


def start_job(user_id: int, opts: dict, source: str = "web") -> str:
    ok, msg = can_start_scan(user_id)
    if not ok:
        raise PermissionError(msg)

    ensure_dirs()
    opts = normalize_opts_for_user(user_id, opts)

    if not opts.get("from_raw") and not saas_mode():
        cdp = (opts.get("cdp") or "http://127.0.0.1:9222").strip()
        probe = check_cdp(cdp)
        if not probe["ok"]:
            raise PermissionError(probe["message"])
    elif not opts.get("from_raw") and saas_mode():
        probe = check_cdp(server_cdp_url())
        if not probe["ok"]:
            raise PermissionError(
                "Scan system maintenance (Chrome server not ready). "
                "Admin must run Chrome debug on the VPS."
            )
    job_id = new_job_id()
    db.insert_job(job_id, user_id, opts, source=source)

    meta = {
        "id": job_id,
        "user_id": user_id,
        "status": "queued",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "opts": opts,
    }
    save_job_meta(meta)

    cmd = build_r_command(user_id, job_id, opts)
    thread = threading.Thread(target=_run_subprocess, args=(user_id, job_id, cmd), daemon=True)
    thread.start()
    return job_id


CDP_HELP = (
    "Chrome debug is not running. Run start_chrome_debug.bat, log into Facebook, "
    "keep Chrome open, then click Check connection again."
)


def check_cdp(cdp_url: str = "http://127.0.0.1:9222") -> dict:
    base = (cdp_url or "http://127.0.0.1:9222").rstrip("/")
    version_url = f"{base}/json/version"
    try:
        req = urllib.request.Request(version_url, headers={"User-Agent": "WinnerSpy"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        browser_name = data.get("Browser") or data.get("browser") or "Chrome"
        return {"ok": True, "message": f"Connected — {browser_name}"}
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, ConnectionRefusedError) or "refused" in str(e).lower():
            return {"ok": False, "message": CDP_HELP}
        return {"ok": False, "message": f"Cannot connect to {base}: {reason}"}
    except Exception as e:
        err = str(e)
        if "refused" in err.lower() or "10061" in err:
            return {"ok": False, "message": CDP_HELP}
        return {"ok": False, "message": err}
