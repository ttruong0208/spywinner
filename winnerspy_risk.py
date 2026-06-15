"""Policy, copyright, and seasonality risk helpers for WinnerSpy."""
from __future__ import annotations

from datetime import datetime

# Brands / IP — high policy risk on Meta ads
COPYRIGHT_BRAND_TERMS = (
    "disney", "marvel", "pixar", "star wars", "harry potter", "pokemon", "nintendo",
    "lego", "barbie", "hello kitty", "sanrio", "nike", "adidas", "apple", "iphone",
    "samsung", "gucci", "louis vuitton", "lv ", "chanel", "supreme", "yeezy",
    "mickey mouse", "frozen", "spider-man", "spiderman", "batman", "superman",
)

HIGH_RISK_NICHE_TERMS = (
    "supplement", "diet pill", "weight loss", "fat burner", "keto", "cbd", "thc",
    "gun", "rifle", "pistol", "ammunition", "weapon", "knife", "taser",
    "adult", "18+", "sex toy", "viagra", "cialis", "prescription",
    "miracle cure", "fda approved", "cancer", "diabetes cure",
)

SEASONAL_HINTS: dict[str, tuple[str, ...]] = {
    "summer": (
        "portable ac", "air conditioner", "cooling fan", "misting fan", "pool float",
        "swimsuit", "bikini", "sunscreen", "beach towel", "ice roller", "cooling vest",
    ),
    "winter": (
        "heated jacket", "hand warmer", "snow shovel", "christmas", "halloween",
        "valentine", "easter",
    ),
}

# Month (1-12) when demand typically fades for that bucket
SEASON_FADE_AFTER = {"summer": 9, "winter": 3}  # Sep+ summer weak; Apr+ winter decor weak


def _blob(row: dict) -> str:
    parts = [
        row.get("product") or "",
        row.get("sample_slug") or row.get("slug") or "",
        row.get("sample_domain") or row.get("domain") or "",
        row.get("sample_url") or "",
    ]
    if isinstance(row.get("keywords"), (list, tuple)):
        parts.extend(row.get("keywords") or [])
    elif row.get("keywords"):
        parts.append(str(row.get("keywords")))
    return " ".join(str(p) for p in parts).lower()


def assess_policy_risk(row: dict) -> dict:
    text = _blob(row)
    hits: list[str] = []
    level = "low"

    for term in COPYRIGHT_BRAND_TERMS:
        if term in text:
            hits.append(f"copyright:{term}")
    for term in HIGH_RISK_NICHE_TERMS:
        if term in text:
            hits.append(f"niche:{term}")

    if any(h.startswith("niche:") for h in hits):
        level = "high"
    elif len([h for h in hits if h.startswith("copyright:")]) >= 2:
        level = "high"
    elif hits:
        level = "medium"

    return {
        "policy_risk": level,
        "policy_hits": hits[:8],
        "policy_note_vi": _policy_note_vi(level, hits),
    }


def _policy_note_vi(level: str, hits: list[str]) -> str:
    if level == "high":
        return "Ngách/bản quyền rủi ro cao — dễ vi phạm policy Meta, cân nhắc tránh."
    if level == "medium":
        return "Có dấu hiệu brand/IP hoặc ngách nhạy cảm — kiểm tra policy trước khi chạy."
    return ""


def assess_seasonality_risk(row: dict, month: int | None = None) -> dict:
    month = month or datetime.now().month
    text = _blob(row)
    bucket = ""
    for name, terms in SEASONAL_HINTS.items():
        if any(t in text for t in terms):
            bucket = name
            break

    gt_label = (row.get("gt_label") or "").strip().lower()
    risk = "none"
    note = ""

    if bucket:
        fade_after = SEASON_FADE_AFTER.get(bucket, 12)
        if month >= fade_after and bucket == "summer":
            risk = "season_fading"
            note = "Sản phẩm mùa hè — max_days cao vào cuối mùa có thể là tín hiệu đang tắt, không phải evergreen."
        elif month >= fade_after and bucket == "winter" and month > 3:
            risk = "season_fading"
            note = "Sản phẩm mùa đông/lễ — kiểm tra xu hướng hiện tại trước khi vào."

    if gt_label in ("low", "falling", "declining"):
        risk = risk if risk != "none" else "trend_declining"
        note = note or "Google Trends giảm — longevity cao có thể là quán tín, không phải cơ hội mới."

    return {
        "seasonality_bucket": bucket,
        "seasonality_risk": risk,
        "seasonality_note_vi": note,
    }


def policy_score_penalty(level: str) -> int:
    if level == "high":
        return 18
    if level == "medium":
        return 8
    return 0


def seasonality_score_penalty(risk: str, max_days: int) -> int:
    if risk == "season_fading" and max_days >= 60:
        return 6
    if risk == "trend_declining" and max_days >= 90:
        return 4
    return 0
