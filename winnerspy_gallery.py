"""Thư viện ads kiểu AdSpy — đọc raw_ads + gắn điểm winner."""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

from winnerspy_filters import MARKETPLACE_MARKERS

CTA_PATTERNS = (
    (r"shop\s*now", "Shop now"),
    (r"learn\s*more", "Learn more"),
    (r"sign\s*up", "Sign up"),
    (r"mua\s*ngay", "Buy now"),
    (r"xem\s*th[eê]m", "View more"),
    (r"đặt\s*hàng", "Order now"),
    (r"order\s*now", "Order now"),
)

NOISE_LINES = re.compile(
    r"library id|id thư viện|started running|ngày bắt đầu|see ad details|"
    r"xem chi tiết|low impressions|ít lượt hiển thị|open dropdown",
    re.I,
)


def _clean_raw_text(raw: str) -> str:
    text = (raw or "").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or NOISE_LINES.search(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def parse_ad_display(raw_text: str, product: str, page: str) -> tuple[str, str, str]:
    body = _clean_raw_text(raw_text)
    short_body = " ".join(body.split())[:420]
    prod = (product or "").strip()
    if prod in ("unknown", "none", ""):
        headline = (page or "Ad").strip()[:100]
    else:
        headline = prod[:120]
    cta = "Learn more"
    blob = (short_body + " " + headline).lower()
    for pat, label in CTA_PATTERNS:
        if re.search(pat, blob, re.I):
            cta = label
            break
    if re.search(r"shop|mua|buy|store", blob, re.I):
        cta = "Shop now"
    return headline, short_body or headline, cta


def media_kind(media_url: str) -> str:
    u = (media_url or "").lower()
    if not u:
        return "none"
    if "video" in u or ".mp4" in u or ".webm" in u:
        return "video"
    return "image"


def library_url(ad_id: str) -> str:
    if not ad_id:
        return "https://www.facebook.com/ads/library/"
    return f"https://www.facebook.com/ads/library/?id={ad_id}"


def load_winner_ad_lookup(job_dir: Path) -> dict[str, dict]:
    path = job_dir / "winner_products.csv"
    if not path.is_file():
        return {}
    lookup: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            ids_raw = row.get("ad_ids") or ""
            ids = re.findall(r"\d{8,}", ids_raw)
            info = {
                "win_score": row.get("win_score") or "",
                "label": row.get("label") or "",
                "product": row.get("product") or "",
                "confidence": row.get("confidence") or "",
            }
            for aid in ids:
                lookup[aid] = info
    return lookup


def load_raw_ads(job_dir: Path, limit: int = 500) -> list[dict]:
    path = job_dir / "raw_ads.csv"
    if not path.is_file():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(dict(row))
    rows.sort(key=lambda r: int(r.get("days") or 0), reverse=True)
    return rows[:limit]


def raw_row_to_card(row: dict, winner_lookup: dict[str, dict], country: str = "US") -> dict:
    ad_id = (row.get("id") or "").strip()
    page = (row.get("page") or "unknown").strip()
    product = (row.get("product") or "").strip()
    raw_text = row.get("ad_copy") or row.get("raw_text") or ""
    media_url = (row.get("media_url") or "").strip()
    headline, body, cta = parse_ad_display(raw_text, product, page)
    domain = (row.get("domain") or "").strip()
    landing = (row.get("clean_url") or row.get("landing_url") or "").strip()
    days = int(row.get("days") or 0)
    win = winner_lookup.get(ad_id, {})
    mtype = row.get("media_type") or media_kind(media_url)
    cc = (row.get("country") or country or "US").strip().upper()

    today = date.today().isoformat()
    started = ""
    if days > 0:
        started = f"~{days} days ago"

    return {
        "id": ad_id,
        "page": page,
        "product": product,
        "headline": headline,
        "body": body,
        "cta": cta,
        "media_url": media_url,
        "media_type": mtype,
        "domain": domain,
        "landing_url": landing,
        "landing_type": row.get("landing_type") or "",
        "keyword": row.get("keyword") or "",
        "country": cc,
        "days": days,
        "started_label": started,
        "last_seen": today,
        "library_url": library_url(ad_id),
        "win_score": win.get("win_score", ""),
        "label": win.get("label", ""),
        "winner_product": win.get("product", ""),
        "is_winner": bool(win.get("win_score")),
    }


def build_gallery_cards(
    job_dir: Path,
    *,
    limit: int = 200,
    country: str = "US",
    only_winners: bool = False,
    media: str = "any",
    min_days: int = 0,
    q: str = "",
) -> list[dict]:
    lookup = load_winner_ad_lookup(job_dir)
    raw = load_raw_ads(job_dir, limit=2000)
    cards = [raw_row_to_card(r, lookup, country) for r in raw]

    q = (q or "").strip().lower()
    media = (media or "any").lower()
    out = []
    for c in cards:
        if only_winners and not c["is_winner"]:
            continue
        if min_days and c["days"] < min_days:
            continue
        if media == "video" and c["media_type"] != "video":
            continue
        if media == "image" and c["media_type"] == "video":
            continue
        if q:
            blob = f"{c['body']} {c['page']} {c['product']} {c['domain']}".lower()
            if q not in blob:
                continue
        domain_l = c["domain"].lower()
        if any(m in domain_l for m in MARKETPLACE_MARKERS):
            if media == "any":  # still show unless filter_no_mp in UI
                pass
        out.append(c)
        if len(out) >= limit:
            break
    return out


def cards_to_json(cards: list[dict]) -> list[dict]:
    return cards
