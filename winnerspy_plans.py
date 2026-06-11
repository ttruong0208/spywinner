"""Gói Free / Pro / VIP — giới hạn quét, keyword, TikTok, Google Trends."""
from __future__ import annotations

from r import KEYWORD_PRESETS


PLANS = {
    "free": {
        "scans_per_day": 5,
        "keywords_max": 3,
        "tiktok": False,
        "tiktok_max": 0,
        "google_trends": False,
        "gt_max": 0,
        "scroll_max": 10,
        "top_max": 25,
        "api": False,
        "schedules": 1,
    },
    "pro": {
        "scans_per_day": 40,
        "keywords_max": 12,
        "tiktok": True,
        "tiktok_max": 15,
        "google_trends": False,
        "gt_max": 0,
        "scroll_max": 18,
        "top_max": 50,
        "api": True,
        "schedules": 5,
    },
    "vip": {
        "scans_per_day": 200,
        "keywords_max": 30,
        "tiktok": True,
        "tiktok_max": 50,
        "google_trends": True,
        "gt_max": 30,
        "scroll_max": 25,
        "top_max": 100,
        "api": True,
        "schedules": 99,
    },
}

# Admin = nội bộ, quota cao
PLANS["admin"] = {**PLANS["vip"], "scans_per_day": 9999, "keywords_max": 999}

CHOOSABLE_PLANS = ("free", "pro", "vip")
PLAN_RANK = {"free": 0, "pro": 1, "vip": 2, "admin": 99}
PLAN_DISPLAY = {"free": "Free", "pro": "Pro", "vip": "VIP"}


def normalize_choose_plan(plan: str | None) -> str:
    p = (plan or "free").strip().lower()
    return p if p in CHOOSABLE_PLANS else "free"


def effective_plan(plan: str) -> str:
    return "vip" if plan == "admin" else plan


def plan_rank(plan: str) -> int:
    return PLAN_RANK.get(plan, 0)


def plan_feature_labels(plan: str) -> dict:
    """Customer-facing plan bullets — honest limits."""
    L = plan_limits(plan)
    return {
        "scans": f"{L['scans_per_day']} scans / day",
        "keywords": f"Up to {L['keywords_max']} keywords / scan",
        "tiktok": (
            f"TikTok: up to {L['tiktok_max']} products / report"
            if L.get("tiktok")
            else "No TikTok"
        ),
        "trends": (
            f"Google Trends: up to {L['gt_max']} products / report"
            if L.get("google_trends")
            else "No Google Trends"
        ),
        "tagline": {
            "free": "Try it — Facebook only",
            "pro": "Small agency — add TikTok",
            "vip": "Full stack — FB + TikTok + Trends",
        }.get(plan, ""),
    }


def plan_limits(plan: str) -> dict:
    return dict(PLANS.get(plan, PLANS["free"]))


def parse_keyword_lines(text: str) -> list[str]:
    if not text:
        return []
    return [k.strip() for k in text.replace(",", "\n").split("\n") if k.strip() and not k.strip().startswith("#")]


def resolve_keywords(opts: dict, limits: dict) -> tuple[str, int]:
    """
    Trả về (keywords multiline, số keyword) đã cắt theo gói.
    Free: tối đa 3 keyword / lần quét.
    """
    max_k = int(limits.get("keywords_max", 3))
    custom = parse_keyword_lines((opts.get("keywords") or "").strip())
    preset = (opts.get("preset") or "").strip()

    if custom:
        chosen = custom[:max_k]
    elif preset and preset in KEYWORD_PRESETS:
        chosen = list(KEYWORD_PRESETS[preset])[:max_k]
    else:
        chosen = []

    if not chosen:
        raise ValueError(
            f"Enter at least 1 keyword (one per line, max {max_k} on your plan)."
        )

    if len(custom) > max_k:
        raise ValueError(
            f"Your plan allows max {max_k} keywords per scan "
            f"(you entered {len(custom)}). Upgrade to Pro/VIP."
        )

    return "\n".join(chosen), len(chosen)
