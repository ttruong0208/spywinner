#!/usr/bin/env python3
"""Scheduled scans for WinnerSpy v5."""
from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

import web_jobs as jobs
import winnerspy_db as db

_scheduler: BackgroundScheduler | None = None


def _run_due_schedules():
    now = datetime.now()
    weekday = str(now.weekday())
    for sch in db.list_enabled_schedules():
        days = set((sch.get("days") or "0,1,2,3,4,5,6").split(","))
        if weekday not in days:
            continue
        if now.hour != int(sch["hour"]) or now.minute != int(sch["minute"]):
            continue
        last = sch.get("last_run_at") or ""
        if last.startswith(now.date().isoformat()):
            continue
        user_id = sch["user_id"]
        try:
            opts = dict(sch["opts"])
            opts["schedule_name"] = sch["name"]
            jobs.start_job(user_id, opts, source="schedule")
            db.touch_schedule_run(sch["id"])
        except Exception:
            pass


def start_scheduler():
    global _scheduler
    if _scheduler:
        return _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_run_due_schedules, "interval", minutes=1, id="winnerspy_schedules")
    _scheduler.start()
    return _scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
