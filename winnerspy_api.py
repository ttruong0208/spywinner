#!/usr/bin/env python3
"""REST API v1 for WinnerSpy v5."""
from __future__ import annotations

import csv
from functools import wraps

from flask import Blueprint, jsonify, request

import web_jobs as jobs
import winnerspy_auth as auth
import winnerspy_db as db

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            key = auth[7:].strip()
        else:
            key = request.headers.get("X-API-Key", "").strip()
        user = db.get_user_by_api_key(key) if key else None
        if not user:
            return jsonify({"error": "Invalid API key"}), 401
        limits = db.plan_limits(user["plan"])
        if not limits["api"]:
            return jsonify({"error": "Plan does not include API access"}), 403
        if not auth.is_user_email_verified(user):
            return jsonify({"error": "Email not verified. Check your inbox for the verification link."}), 403
        request.api_user = user
        return fn(*args, **kwargs)

    return wrapper


@bp.route("/me")
@require_api_key
def api_me():
    u = request.api_user
    limits = db.plan_limits(u["plan"])
    return jsonify({
        "email": u["email"],
        "plan": u["plan"],
        "limits": limits,
        "scans_today": db.count_scans_today(u["id"]),
    })


@bp.route("/scans", methods=["POST"])
@require_api_key
def api_create_scan():
    u = request.api_user
    data = request.get_json(silent=True) or {}
    opts = {
        "country": data.get("country", "US"),
        "preset": data.get("preset", "cleaning_us"),
        "keywords": data.get("keywords", ""),
        "scroll": data.get("scroll", 8),
        "top": data.get("top", 20),
        "tiktok": bool(data.get("tiktok", True)),
        "tiktok_limit": data.get("tiktok_limit", 15),
        "cdp": data.get("cdp") or u.get("cdp_url"),
        "from_raw": bool(data.get("from_raw", False)),
    }
    try:
        job_id = jobs.start_job(u["id"], opts, source="api")
    except PermissionError as e:
        return jsonify({"error": str(e)}), 429
    return jsonify({"job_id": job_id, "status": "queued"}), 201


@bp.route("/scans/<job_id>")
@require_api_key
def api_get_scan(job_id):
    u = request.api_user
    job = db.get_job(job_id)
    if not job or job["user_id"] != u["id"]:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "job_id": job_id,
        "status": job["status"],
        "opts": job["opts"],
        "exit_code": job.get("exit_code"),
        "created_at": job["created_at"],
        "finished_at": job.get("finished_at"),
        "log_tail": jobs.tail_log(u["id"], job_id, 40),
    })


@bp.route("/scans/<job_id>/winners")
@require_api_key
def api_get_winners(job_id):
    u = request.api_user
    job = db.get_job(job_id)
    if not job or job["user_id"] != u["id"]:
        return jsonify({"error": "Not found"}), 404

    d = jobs.job_path(u["id"], job_id)
    for name in ("final_research_results.csv", "winner_products.csv"):
        p = d / name
        if not p.is_file():
            continue
        with p.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        label = request.args.get("label")
        if label:
            rows = [r for r in rows if (r.get("label") or "") == label]
        return jsonify({"job_id": job_id, "count": len(rows), "winners": rows[:100]})
    return jsonify({"job_id": job_id, "count": 0, "winners": []})
