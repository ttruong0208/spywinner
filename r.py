#!/usr/bin/env python3
import os
import sys
import time
import argparse

# Windows console: tránh UnicodeEncodeError khi in tiếng Việt
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
import re
import csv
import hashlib
import statistics
import urllib.parse
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict
from playwright.sync_api import sync_playwright

# =========================
# CONFIG
# =========================
KEYWORD_PRESETS = {
    "cleaning_us": [
        "no bending cleaning tool",
        "lazy cleaning gadget",
        "hard to reach cleaning tool",
        "360 cleaning brush",
        "multifunctional cleaning brush",
        "reusable cleaning tool",
    ],
    "cleaning_vn": [
        "cây lau nhà",
        "dụng cụ vệ sinh",
        "bàn chải vệ sinh",
        "dụng cụ tẩy rửa",
    ],
    "home_gadget_us": [
        "home gadget",
        "kitchen gadget",
        "organizer tool",
    ],
}

KEYWORDS = list(KEYWORD_PRESETS["cleaning_us"])
COUNTRY = "US"
SCROLL_ROUNDS = 8
TOP_N = 20
REPORT_MIN_PRODUCTS = 5
REPORT_MAX_PRODUCTS = 7
DEBUG = False

USE_CDP = True
CDP_URL = "http://127.0.0.1:9222"


def apply_runtime_config(
    country=None,
    keywords=None,
    scroll_rounds=None,
    top_n=None,
    cdp_url=None,
):
    """Override module config from CLI."""
    global COUNTRY, KEYWORDS, SCROLL_ROUNDS, TOP_N, CDP_URL
    if country:
        COUNTRY = country.upper()
    if keywords:
        KEYWORDS = list(keywords)
    if scroll_rounds is not None:
        SCROLL_ROUNDS = int(scroll_rounds)
    if top_n is not None:
        TOP_N = int(top_n)
    if cdp_url:
        CDP_URL = cdp_url

BAD_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "amazon.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "pinterest.com",
    "ebay.com",
    "walmart.com",
    "etsy.com",
    "temu.com",
    "aliexpress.com",
}

BAD_SLUGS = {
    "", "none", "products", "product", "collections", "collection",
    "shop", "store", "catalog", "search", "all", "item", "items",
    "home", "homepage", "index"
}

NICHE_WORDS = [
    "clean", "cleaning", "brush", "scrub", "scrubber", "remover",
    "organizer", "storage", "drain", "mold", "lint", "pet", "hair",
    "kitchen", "sink", "repair", "zipper", "gel", "filter", "sealer",
    "spray", "fridge", "tile", "gap", "groove", "window", "bathroom",
    "toilet", "grout", "stain", "dust", "odor",
]

BAD_DOMAIN_WORDS = [
    "novel", "story", "reader", "fiction", "drama", "episode",
    "movie", "video", "short", "tv", "stream", "comic", "manga",
    "webnovel", "novelbox", "soda",
]

BAD_PRODUCT_WORDS = [
    "synopsis", "chapter", "episode", "watch", "read", "novel",
    "story", "drama", "movie", "series", "season", "book",
]

GOOD_NICHE_WORDS = [
    "clean", "cleaning", "brush", "scrub", "scrubber", "remover",
    "dust", "stain", "mold", "drain", "grout", "toilet", "bathroom",
    "sink", "spray", "lint", "pet", "hair", "kitchen", "bag",
    "sealer", "storage", "organizer", "filter", "strainer", "repair",
    "zipper", "tile", "gap", "window", "odor", "fresh",
]

BAD_EXACT_DOMAINS = {"fb.me", "fb.com", "facebook.com", "messenger.com", "walmart.com"}
BAD_DOMAIN_PARTS = ["buyerswiki", "pagefly", "messenger_doc"]
BAD_SLUG_WORDS = {"unknown", "none", "pagefly", "synopsis", "messenger_doc", "homepage"}

# Dịch vụ / lead form — không phải SP physical dropship
SERVICE_PHRASES = [
    "professionally cleans", "curbside", "sanitizes", "deodorizes", "trash bin",
    "recycling bin", "garbage can", "junk removal", "maid service", "house cleaning service",
    "carpet cleaning service", "pressure washing", "book a cleaning", "schedule now",
    "first cleaning visit", "promo code", "get on our schedule", "bins curbside",
    "cleaning visit", "lawn care", "pest control", "plumbing service", "hvac",
]

SIGNATURE_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "pro", "plus",
    "set", "kit", "pack", "pcs", "piece", "pieces", "new", "best",
    "shop", "store", "product", "products", "official", "sale", "buy",
    "get", "all", "home", "item", "items", "v2", "v3", "page", "landing",
    "to", "a", "an", "of", "in", "on", "by", "at", "up", "ultra", "max",
}

FREQUENCY_TOKEN_BLACKLIST = {
    "clean", "cleaning", "product", "products", "tool", "gadget",
    "hack", "satisfying", "bathroom", "kitchen", "home",
}

import json

# ====
# TIKTOK RESEARCH MODULE
# ====

def convert_tiktok_view(text):
    text = text.lower().replace('lượt xem', '').replace('views', '').strip()
    if not text:
        return 0
    try:
        if 'm' in text:
            return int(float(text.replace('m', '')) * 1_000_000)
        if 'k' in text:
            return int(float(text.replace('k', '')) * 1_000)
        return int(''.join(filter(str.isdigit, text)))
    except Exception:
        return 0


def _tiktok_result_base(tt_label="cold", tt_status="ok"):
    return {
        "tt_top_views": 0,
        "tt_total_samples": 0,
        "tt_trending_score": 0,
        "tt_label": tt_label,
        "tt_status": tt_status,
    }


def tiktok_error_banner_visible(page) -> bool:
    """Chỉ coi là lỗi khi banner lỗi hiện — không dựa vào cả body (dễ dư text cũ)."""
    try:
        err = page.get_by_text("Đã xảy ra lỗi", exact=False)
        if err.count() > 0 and err.first.is_visible():
            return True
        err_en = page.get_by_text("Something went wrong", exact=False)
        if err_en.count() > 0 and err_en.first.is_visible():
            return True
    except Exception:
        pass
    return False


def _tiktok_wait_for_content(page, max_wait_sec=18) -> bool:
    """Đợi video/search card — giống user mở tab, vài giây sau mới có kết quả."""
    selectors = (
        'strong[data-e2e*="video-views"]',
        '[data-e2e="search-card-video"]',
        'a[href*="/video/"]',
        'div[data-e2e="search_video-item"]',
    )
    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    return True
            except Exception:
                continue
        time.sleep(1)
    return False


def shorten_search_query(text: str, max_words: int = 5) -> str:
    """Rút gọn tên SP cho TikTok / Google Trends (cụm dài thường không có dữ liệu)."""
    raw = re.sub(r"[^\w\s-]", " ", (text or "").lower())
    words = [w for w in raw.split() if len(w) > 1]
    stop = {
        "the", "a", "an", "for", "and", "with", "in", "on", "of", "to",
        "kit", "set", "pack", "free", "new", "best", "pro", "plus",
        "mess", "all", "one", "1", "2", "3", "4", "5", "6", "7", "8",
    }
    kept = [w for w in words if w not in stop][:max_words]
    if kept:
        return " ".join(kept)
    return (text or "").strip()[:60]


def _tiktok_collect_views_js(page) -> list[int]:
    try:
        texts = page.evaluate(
            """() => {
                const out = [];
                const nodes = document.querySelectorAll(
                    'strong[data-e2e*="video-views"], strong, span'
                );
                for (const el of nodes) {
                    const t = (el.innerText || '').trim();
                    if (!t || t.length > 40) continue;
                    if (/views|lượt xem|\\d+[.,]?\\d*[KkMm]/i.test(t)) {
                        const inCard = el.closest(
                            'a[href*="/video/"], [data-e2e*="video"], [data-e2e*="search"]'
                        );
                        if (inCard) out.push(t);
                    }
                }
                return [...new Set(out)].slice(0, 16);
            }"""
        )
        views = [convert_tiktok_view(t) for t in (texts or [])]
        return [v for v in views if v > 0]
    except Exception:
        return []


def _tiktok_collect_views(page) -> list[int]:
    views = []
    selectors = (
        'strong[data-e2e*="video-views"]',
        'strong:has-text("views")',
        'strong:has-text("lượt xem")',
        '[data-e2e="search-card-desc"] strong',
    )
    for sel in selectors:
        try:
            locs = page.locator(sel).all()
            for loc in locs[:12]:
                try:
                    v_num = convert_tiktok_view(loc.inner_text())
                    if v_num > 0:
                        views.append(v_num)
                except Exception:
                    continue
            if views:
                break
        except Exception:
            continue
    if not views:
        views = _tiktok_collect_views_js(page)
    return views


def _tiktok_try_reload(page) -> bool:
    for label in ("Thử lại", "Try again"):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() > 0:
                btn.first.click(timeout=3000)
                time.sleep(4)
                return True
        except Exception:
            pass
    try:
        page.reload(wait_until="domcontentloaded", timeout=45000)
        time.sleep(3)
        return True
    except Exception:
        return False


def _tiktok_prepare_page(page) -> None:
    try:
        page.set_viewport_size({"width": 1280, "height": 720})
    except Exception:
        pass
    try:
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
    except Exception:
        pass


def get_tiktok_signals(page, product_name):
    """Search TikTok — đợi SPA load giống user; có video thì đọc view dù banner lỗi còn trên DOM."""
    query = shorten_search_query(product_name) or (product_name or "").strip()
    search_url = f"https://www.tiktok.com/search/video?q={urllib.parse.quote(query)}"
    debug(f"[TIKTOK] Researching: {query} (from: {product_name})")

    results = _tiktok_result_base()
    _tiktok_prepare_page(page)

    for attempt in range(3):
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            _tiktok_wait_for_content(page, max_wait_sec=18)

            try:
                page.mouse.wheel(0, 1200)
                time.sleep(2)
                page.mouse.wheel(0, 1200)
                time.sleep(2)
            except Exception:
                pass

            views = _tiktok_collect_views(page)

            if views:
                results["tt_top_views"] = max(views)
                results["tt_total_samples"] = len(views)
                if results["tt_top_views"] > 1_000_000:
                    results["tt_trending_score"] = 10
                    results["tt_label"] = "EXPLOSIVE"
                elif results["tt_top_views"] > 200_000:
                    results["tt_trending_score"] = 7
                    results["tt_label"] = "TRENDING"
                elif results["tt_top_views"] > 50_000:
                    results["tt_trending_score"] = 4
                    results["tt_label"] = "POTENTIAL"
                else:
                    results["tt_trending_score"] = 1
                    results["tt_label"] = "COLD"
                results["tt_status"] = "ok"
                return results

            has_err = tiktok_error_banner_visible(page)
            if has_err:
                print(f"  [TIKTOK] Chua thay video (co banner loi) — thu lai {attempt + 1}/3")
            else:
                print(f"  [TIKTOK] Chua thay video — thu lai {attempt + 1}/3")

            if attempt < 2 and _tiktok_try_reload(page):
                _tiktok_wait_for_content(page, max_wait_sec=10)
                continue

        except Exception as e:
            debug(f"[TIKTOK] Error: {e}")
            if attempt < 2 and _tiktok_try_reload(page):
                continue

    if tiktok_error_banner_visible(page):
        return _tiktok_result_base(tt_label="unavailable", tt_status="tiktok_error")
    results["tt_label"] = "no_data"
    results["tt_status"] = "empty"
    return results

def pick_tiktok_query(row):
    """English product name works best on TikTok search (short query)."""
    product = (row.get("product") or "").strip()
    if product and product.lower() not in {"unknown", "none"}:
        return shorten_search_query(product)
    signature = (row.get("signature") or "").strip()
    if signature:
        return shorten_search_query(signature)
    return shorten_search_query(
        slug_to_name(row.get("sample_slug") or row.get("slug") or "")
    )


def pick_gtrends_query(row):
    """Google Trends: chỉ dùng tên SP (cột product), không rút gọn."""
    product = (row.get("product") or "").strip()
    if product and product.lower() not in {"unknown", "none"}:
        return product
    return ""


def _combine_tiktok_row(row, tt_data, query):
    combined_row = {**row, **tt_data, "tiktok_query": query}
    try:
        win_score = float(row.get("win_score") or 0)
    except (TypeError, ValueError):
        win_score = 0.0
    if tt_data.get("tt_status") in ("tiktok_error", "error", "skipped"):
        combined_row["final_priority"] = round(win_score, 2)
    else:
        combined_row["final_priority"] = round(
            win_score + (tt_data["tt_trending_score"] * 2), 2
        )
    return combined_row


def _write_tiktok_csv(final_data, output_csv):
    if not final_data:
        return None
    final_data.sort(
        key=lambda x: float(x.get("final_priority") or 0),
        reverse=True,
    )
    keys = list(final_data[0].keys())
    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(final_data)
    print(f"\n✅ TikTok xong: {output_csv}")
    return output_csv


def _tiktok_fallback_rows(pool, reason="skipped"):
    """FB đã xong — vẫn xuất final.csv khi TikTok/CDP lỗi."""
    print(f"\n[TIKTOK] Bo qua check TikTok ({reason}) — giu diem Facebook.")
    rows_out = []
    for row in pool:
        q = pick_tiktok_query(row)
        tt = _tiktok_result_base(tt_label="skipped", tt_status="skipped")
        rows_out.append(_combine_tiktok_row(row, tt, q))
    return rows_out


def run_tiktok_validator(
    input_csv="winner_products.csv",
    output_csv="final_research_results.csv",
    limit=15,
    labels_filter=None,
    pool_rows=None,
):
    labels_filter = labels_filter or {"winner_candidate", "watchlist"}

    if pool_rows is not None:
        rows = list(pool_rows)
    else:
        if not input_csv:
            return None
        rows = []
        try:
            with open(input_csv, "r", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        except OSError:
            print(f"File not found: {input_csv}")
            return None

    if not rows:
        print("No products to check on TikTok.")
        return None

    filtered = [
        r for r in rows
        if (r.get("label") or "").strip() in labels_filter
    ]
    pool = filtered if filtered else rows
    pool = pool[: max(1, int(limit))]

    print(f"\n--- TIKTOK CHECK: {len(pool)} products (from {len(rows)} winners) ---")

    final_data = []
    cdp_failed = False
    ua_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0] if browser.contexts else browser.new_context()

            for idx, row in enumerate(pool, start=1):
                query = pick_tiktok_query(row)
                print(f"[{idx}/{len(pool)}] TikTok: {query}...")
                # Mỗi SP = tab mới (giống user mở tab bên cạnh — tab cũ kẹt lỗi vẫn OK tab mới)
                tik_page = context.new_page()
                try:
                    tik_page.set_extra_http_headers(ua_headers)
                    _tiktok_prepare_page(tik_page)
                    tt_data = get_tiktok_signals(tik_page, query)
                    if tt_data.get("tt_status") == "tiktok_error":
                        print("  → TikTok server error (no views) — still saving product row")
                    final_data.append(_combine_tiktok_row(row, tt_data, query))
                finally:
                    try:
                        tik_page.close()
                    except Exception:
                        pass
                time.sleep(4)
        except Exception as e:
            cdp_failed = True
            print(f"TikTok/CDP error: {e}")
            if "ECONNREFUSED" in str(e) or "refused" in str(e).lower():
                print("  → Run start_chrome_debug.bat again; dismiss any restore popup.")

    if not final_data:
        final_data = _tiktok_fallback_rows(pool, "CDP error" if cdp_failed else "no data")

    return _write_tiktok_csv(final_data, output_csv)


def get_google_trends_signal(keyword, geo="US"):
    """Google Trends (pytrends) — VIP. Không cần Chrome."""
    kw = (keyword or "").strip()
    base = {
        "gt_interest": 0,
        "gt_label": "no data",
        "gt_status": "skipped",
        "gt_query": kw,
    }
    try:
        from pytrends.request import TrendReq
    except ImportError:
        base["gt_status"] = "no_pytrends"
        return base

    if not kw:
        base["gt_status"] = "empty"
        return base

    geo_code = "" if (geo or "").upper() == "ALL" else (geo or "US")
    last_err = ""
    for attempt in range(3):
        try:
            pytrend = TrendReq(
                hl="en-US",
                tz=360,
                timeout=(12, 30),
                retries=2,
                backoff_factor=0.2,
            )
            pytrend.build_payload([kw], timeframe="today 12-m", geo=geo_code)
            df = pytrend.interest_over_time()
            if df is None or df.empty or kw not in df.columns:
                base["gt_status"] = "no_data"
                base["gt_label"] = "no data"
                return base
            series = df[kw]
            recent = float(series.tail(8).mean())
            peak = float(series.max())
            base["gt_interest"] = int(round(recent))
            if recent >= 65 or (peak >= 75 and recent >= 35):
                base["gt_label"] = "rising"
            elif recent >= 25:
                base["gt_label"] = "stable"
            else:
                base["gt_label"] = "low"
            base["gt_status"] = "ok"
            return base
        except Exception as e:
            last_err = str(e)[:120]
            if attempt < 2:
                time.sleep(4 + attempt * 4)
                continue
            base["gt_status"] = "error"
            base["gt_label"] = "error"
            base["gt_note"] = last_err
            return base
    return base


def run_google_trends_enrich(
    input_csv,
    output_csv=None,
    limit=15,
    geo="US",
    labels_filter=None,
):
    """Gắn Google Trends vào CSV (sau bước TikTok nếu có)."""
    if not input_csv or not os.path.isfile(input_csv):
        print(f"Trends CSV not found: {input_csv}")
        return None

    output_csv = output_csv or input_csv
    labels_filter = labels_filter or {"winner_candidate", "watchlist"}

    with open(input_csv, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None

    filtered = [r for r in rows if (r.get("label") or "").strip() in labels_filter]
    pool = filtered if filtered else rows
    pool = pool[: max(1, int(limit))]

    print(f"\n--- GOOGLE TRENDS: {len(pool)} products (geo={geo}) ---")
    gt_by_key = {}
    for r in pool:
        q = pick_gtrends_query(r)
        rk = (r.get("product") or "").strip()
        if not q:
            print("  Trends: skip (no product name)")
            continue
        print(f"  Trends: {q}...")
        gt = get_google_trends_signal(q, geo=geo)
        try:
            fp = float(r.get("final_priority") or r.get("win_score") or 0)
        except (TypeError, ValueError):
            fp = 0.0
        bonus = {"rising": 8, "stable": 3, "low": 0, "no data": 0, "error": 0}.get(
            gt.get("gt_label"), 0
        )
        gt["final_priority"] = round(fp + bonus, 2)
        gt_by_key[rk] = gt
        time.sleep(2)

    enriched = []
    for row in rows:
        r = dict(row)
        rk = (r.get("product") or "").strip()
        if rk in gt_by_key:
            pack = gt_by_key[rk]
            r.update({k: v for k, v in pack.items() if k.startswith("gt_")})
            r["final_priority"] = pack.get("final_priority", r.get("final_priority"))
        else:
            r.setdefault("gt_status", "not_checked")
        enriched.append(r)

    keys = list(enriched[0].keys())
    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(enriched)
    print(f"\n✅ Google Trends xong: {output_csv}")
    return output_csv


def product_row_key(row: dict) -> str:
    return (row.get("signature") or row.get("product") or "").strip()


def quality_tier(row: dict) -> dict:
    """Nhãn chất lượng cho khách chọn SP (Tốt / Khá / Trung bình / Kém)."""
    try:
        score = float(row.get("final_priority") or row.get("win_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    label = (row.get("label") or "").strip()

    if label == "winner_candidate" or score >= 22:
        return {
            "tier": "good",
            "label": "Tốt",
            "hint": "Tín hiệu mạnh — đáng test landing/creative",
            "css": "tier-good",
        }
    if label == "watchlist" or score >= 16:
        return {
            "tier": "ok",
            "label": "Khá",
            "hint": "Có tiềm năng — theo dõi thêm",
            "css": "tier-ok",
        }
    if label == "testing" or score >= 10:
        return {
            "tier": "mid",
            "label": "Trung bình",
            "hint": "Mới hoặc ít ads — cân nhắc kỹ",
            "css": "tier-mid",
        }
    return {
        "tier": "low",
        "label": "Kém",
        "hint": "Ít bằng chứng — chỉ tham khảo",
        "css": "tier-low",
    }


def load_csv_rows(path) -> list:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def merge_enrichment_rows(scored: list, enriched: list) -> list:
    """Gắn TikTok/Trends từ final.csv lên toàn bộ scored."""
    by_key = {product_row_key(r): r for r in enriched if product_row_key(r)}
    out = []
    for row in scored:
        r = dict(row)
        extra = by_key.get(product_row_key(r))
        if extra:
            for k, v in extra.items():
                if str(k).startswith(("tt_", "gt_")) or k == "final_priority":
                    r[k] = v
        out.append(r)
    return out


def pick_report_products(rows: list, min_n=None, max_n=None) -> list:
    """Top 5–7 SP theo điểm — để khách chọn, không chỉ 1 winner."""
    min_n = REPORT_MIN_PRODUCTS if min_n is None else min_n
    max_n = REPORT_MAX_PRODUCTS if max_n is None else max_n
    if not rows:
        return []
    sorted_rows = sorted(
        rows,
        key=lambda r: float(r.get("final_priority") or r.get("win_score") or 0),
        reverse=True,
    )
    if len(sorted_rows) >= min_n:
        return sorted_rows[: min(max_n, len(sorted_rows))]
    return sorted_rows


def ad_library_link(ad_ids_raw: str) -> tuple[str, int]:
    """URL Ads Library + số ad id trong nhóm."""
    ids = re.findall(r"\d{8,}", ad_ids_raw or "")
    if not ids:
        return "", 0
    return f"https://www.facebook.com/ads/library/?id={ids[0]}", len(ids)


def build_report_product_rows(job_dir, min_n=None, max_n=None) -> list:
    """Ưu tiên scored_products.csv (đủ SP), merge enrichment từ final."""
    job_dir = Path(job_dir)
    scored_p = job_dir / "scored_products.csv"
    final_p = job_dir / "final_research_results.csv"
    winners_p = job_dir / "winner_products.csv"

    scored = load_csv_rows(scored_p) if scored_p.is_file() else []
    if not scored and winners_p.is_file():
        scored = load_csv_rows(winners_p)
    if not scored and final_p.is_file():
        scored = load_csv_rows(final_p)

    enriched = load_csv_rows(final_p) if final_p.is_file() else []
    if not enriched and winners_p.is_file():
        enriched = load_csv_rows(winners_p)

    merged = merge_enrichment_rows(scored, enriched) if enriched else scored
    return pick_report_products(merged, min_n, max_n)


def export_html_report(
    csv_path=None,
    html_path=None,
    title="WinnerSpy — Research Report",
    subtitle_extra: str = "",
    job_dir=None,
    rows=None,
):
    """Báo cáo HTML: top 5–7 SP + nhãn chất lượng (Tốt/Khá/TB/Kém)."""
    if rows is None:
        if job_dir:
            rows = build_report_product_rows(job_dir)
        elif csv_path:
            parent = Path(csv_path).parent
            rows = build_report_product_rows(parent)
            if not rows:
                rows = pick_report_products(load_csv_rows(csv_path))
        else:
            print("export_html_report: no data source")
            return None

    if not rows:
        print("CSV empty — no HTML report.")
        return None

    has_tiktok = any("tt_label" in r for r in rows)
    has_gt = any("gt_label" in r for r in rows)
    winners = sum(1 for r in rows if (r.get("label") or "") == "winner_candidate")
    preset_hits = sum(1 for r in rows if str(r.get("matches_preset") or "") == "1")
    top_score = max(float(r.get("win_score") or r.get("final_priority") or 0) for r in rows)
    sub_extra = subtitle_extra or (
        f"Top {len(rows)} sản phẩm để bạn chọn — nhãn Tốt/Khá/TB/Kém theo điểm & tín hiệu FB"
    )
    if preset_hits and preset_hits < len(rows):
        sub_extra = (
            (sub_extra + " · ").strip(" · ")
            + f"{preset_hits}/{len(rows)} đạt preset filter"
        )
    src_label = str(job_dir or csv_path or "scored_products.csv")

    def esc(text):
        return (
            str(text or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    body_rows = []
    for i, r in enumerate(rows, start=1):
        product = esc(r.get("product") or r.get("signature") or "?")
        domain = esc(r.get("sample_domain") or r.get("domain") or "")
        score = esc(r.get("final_priority") or r.get("win_score") or "")
        tier = quality_tier(r)
        qbadge = (
            f"<span class='qbadge {tier['css']}' title='{esc(tier['hint'])}'>"
            f"{esc(tier['label'])}</span>"
        )
        ads = esc(r.get("ads_count") or "")
        max_days = (r.get("max_days") or "").strip()
        med_days = (r.get("median_days") or "").strip()
        if max_days:
            days_tip = f"median {med_days}d" if med_days else "longest-running ad in group"
            days_cell = f'<span title="{esc(days_tip)}">{esc(max_days)}d</span>'
        else:
            days_cell = "—"
        tt = ""
        gt = ""
        if has_gt:
            gt = f"<td>{esc(r.get('gt_label'))}</td><td>{esc(r.get('gt_interest'))}</td>"
        if has_tiktok:
            tt = (
                f"<td>{esc(r.get('tt_label'))}</td>"
                f"<td>{esc(r.get('tt_top_views'))}</td>"
            )
        shop_url = (r.get("sample_url") or "").strip()
        links = []
        if shop_url:
            links.append(f'<a href="{esc(shop_url)}" target="_blank" rel="noopener" class="lnk">Shop</a>')
        fb_url, fb_n = ad_library_link(r.get("ad_ids") or "")
        if fb_url:
            fb_label = f"FB ×{fb_n}" if fb_n > 1 else "FB Ad"
            links.append(
                f'<a href="{esc(fb_url)}" target="_blank" rel="noopener" class="lnk fb">{fb_label}</a>'
            )
        link_cell = " ".join(links) if links else "—"
        body_rows.append(
            f"<tr><td>{i}</td><td class='score'>{score}</td><td>{qbadge}</td>"
            f"<td>{product}</td><td>{domain}</td><td>{ads}</td><td>{days_cell}</td>"
            f"{tt}{gt}<td class='links'>{link_cell}</td></tr>"
        )

    tt_head = "<th>TikTok</th><th>Views</th>" if has_tiktok else ""
    gt_head = "<th>GTrend</th><th>GT score</th>" if has_gt else ""

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8"/>
  <title>{esc(title)}</title>
  <style>
    body {{ font-family: Segoe UI, sans-serif; background:#f5f7fb; margin:0; padding:24px; color:#1f2937; }}
    h1 {{ margin:0 0 4px; color:#24324a; }}
    .sub {{ color:#6b7280; margin-bottom:20px; font-size:14px; }}
    .stats {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px; }}
    .stat {{ background:#fff; border:1px solid #d9e2ef; border-radius:12px; padding:14px 20px; min-width:120px; }}
    .stat .n {{ font-size:24px; font-weight:800; color:#5b6cff; }}
    .stat .l {{ font-size:12px; color:#6b7280; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,.05); }}
    th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid #e5e7eb; font-size:13px; }}
    th {{ background:#eef2ff; color:#374151; font-size:11px; text-transform:uppercase; }}
    .score {{ color:#059669; font-weight:700; }}
    .qbadge {{ padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700; white-space:nowrap; }}
    .tier-good {{ background:#d1fae5; color:#065f46; }}
    .tier-ok {{ background:#dbeafe; color:#1e40af; }}
    .tier-mid {{ background:#fef3c7; color:#92400e; }}
    .tier-low {{ background:#f3f4f6; color:#6b7280; }}
    .links .lnk {{ display:inline-block; margin-right:6px; padding:2px 8px; border-radius:6px;
      background:#eef2ff; color:#4338ca; text-decoration:none; font-size:11px; font-weight:600; }}
    .links .lnk.fb {{ background:#e0f2fe; color:#0369a1; }}
    .links .lnk:hover {{ text-decoration:underline; }}
    .note {{ margin-top:16px; font-size:12px; color:#6b7280; }}
  </style>
</head>
<body>
  <h1>{esc(title)}</h1>
  <p class="sub">Facebook Ads Library ({esc(COUNTRY)}) • {esc(src_label)} • {datetime.now().strftime('%Y-%m-%d %H:%M')}{(' · ' + esc(sub_extra)) if sub_extra else ''}</p>
  <div class="stats">
    <div class="stat"><div class="n">{len(rows)}</div><div class="l">Products</div></div>
    <div class="stat"><div class="n">{winners}</div><div class="l">Winner candidates</div></div>
    <div class="stat"><div class="n">{int(top_score)}</div><div class="l">Top score</div></div>
  </div>
  <table>
    <thead>
      <tr><th>#</th><th>Score</th><th>Quality</th><th>Product</th><th>Domain</th><th>Ads</th><th>Days</th>{tt_head}{gt_head}<th>Links</th></tr>
    </thead>
    <tbody>
      {''.join(body_rows)}
    </tbody>
  </table>
  <p class="note">Days = ad chạy lâu nhất trong nhóm · FB Ad = mở thẳng Facebook Ads Library.
  Tốt/Khá/TB/Kém = gợi ý chất lượng. Ctrl+P → Save as PDF.</p>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML report: {html_path}")
    return html_path
# =========================
# HELPERS
# =========================
def debug(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)


def normalize_domain(hostname):
    hostname = (hostname or "").lower().strip()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname or "unknown"


def normalize_text(text):
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s\-_]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def numeric(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def slug_to_name(slug):
    slug = (slug or "").strip("-_ ")
    if not slug:
        return "unknown"
    return slug.replace("-", " ").replace("_", " ").strip()


def decode_facebook_redirect(href):
    if not href:
        return None
    try:
        if "l.facebook.com/l.php?u=" in href or "facebook.com/l.php?u=" in href:
            query = urllib.parse.urlparse(href).query
            real = urllib.parse.parse_qs(query).get("u", [None])[0]
            return urllib.parse.unquote(real) if real else None
        return href
    except Exception:
        return None


def clean_landing_url(url):
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        domain = normalize_domain(parsed.hostname)
        path = parsed.path or ""
        clean = f"{parsed.scheme}://{domain}{path}".rstrip("/")
        return clean
    except Exception:
        return url


def extract_info_from_url(url):
    if not url:
        return {
            "clean_url": "",
            "domain": "unknown",
            "slug": "none",
            "product": "unknown",
            "landing_type": "unknown",
        }

    try:
        parsed = urllib.parse.urlparse(url)
        domain = normalize_domain(parsed.hostname)
        path = (parsed.path or "").strip("/")
        parts = [p for p in path.split("/") if p.strip()]

        slug = parts[-1].lower() if parts else "none"
        slug = re.sub(r"[^a-z0-9\-_]+", "-", slug).strip("-")
        if not slug:
            slug = "none"

        product = slug_to_name(slug)
        clean_url = clean_landing_url(url)

        if not parts:
            landing_type = "homepage"
        elif slug in BAD_SLUGS:
            landing_type = "generic"
        elif "product" in path or "products" in path:
            landing_type = "product"
        else:
            landing_type = "product"

        return {
            "clean_url": clean_url,
            "domain": domain,
            "slug": slug,
            "product": product if product else "unknown",
            "landing_type": landing_type,
        }
    except Exception:
        return {
            "clean_url": "",
            "domain": "unknown",
            "slug": "none",
            "product": "unknown",
            "landing_type": "unknown",
        }


def has_low_impression(raw_text):
    text = (raw_text or "").lower()
    return "ít lượt hiển thị" in text or "low impressions" in text


def parse_start_days(text):
    text = text or ""

    m = re.search(r"Started running on\s+([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", text, re.I)
    if m:
        date_str = m.group(1).strip()
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"):
            try:
                start_date = datetime.strptime(date_str, fmt)
                return max((datetime.now() - start_date).days, 1)
            except Exception:
                pass

    m = re.search(r"Ngày bắt đầu chạy:?\s*(\d{1,2})\s+Tháng\s+(\d{1,2}),\s*(\d{4})", text, re.I)
    if m:
        try:
            day, month, year = map(int, m.groups())
            start_date = datetime(year, month, day)
            return max((datetime.now() - start_date).days, 1)
        except Exception:
            pass

    return 1


def niche_bonus(product, slug, domain):
    text = f"{product} {slug} {domain}".lower()
    score = 0
    for w in NICHE_WORDS:
        if w in text:
            score += 1
    return min(score, 4)


def relevance_score(*parts):
    text = " ".join([p for p in parts if p]).lower()
    hits = sum(1 for w in GOOD_NICHE_WORDS if w in text)
    if hits == 0:
        return -4
    if hits == 1:
        return -1
    if hits == 2:
        return 1
    if hits == 3:
        return 3
    return 5


def is_low_quality_product(domain, slug, product, sample_url=""):
    d = (domain or "").lower()
    s = (slug or "").lower()
    p = (product or "").lower()
    _ = (sample_url or "").lower()

    if d in BAD_EXACT_DOMAINS:
        return True
    if any(x in d for x in BAD_DOMAIN_PARTS):
        return True
    if s in BAD_SLUG_WORDS or p in BAD_SLUG_WORDS:
        return True
    if re.fullmatch(r"\d{6,}", s):
        return True
    if re.fullmatch(r"(adv|f)\d+", s):
        return True
    return False


def is_bad_candidate(product, domain, pages, sample_url):
    text = " ".join([
        product or "",
        domain or "",
        " ".join(pages or []),
        sample_url or "",
    ]).lower()
    bad_words = BAD_DOMAIN_WORDS + BAD_PRODUCT_WORDS
    return any(w in text for w in bad_words)


def is_service_listing(product, pages, sample_url, raw_snippets=None):
    text = " ".join([
        product or "",
        " ".join(pages or []),
        sample_url or "",
        " ".join(raw_snippets or []),
    ]).lower()
    if any(p in text for p in SERVICE_PHRASES):
        return True
    if "messenger" in text or "messenger_doc" in text:
        return True
    return False


def is_junk_product_row(row):
    """Loại hàng rác khỏi báo cáo chính — không đưa lên top."""
    domain = normalize_domain(row.get("sample_domain", ""))
    product = normalize_text(row.get("product", ""))
    url = (row.get("sample_url") or "").lower()
    landing = row.get("landing_type", "unknown")
    pages = row.get("pages") or []
    rel = numeric(row.get("relevance_score", 0), 0)

    if domain in BAD_EXACT_DOMAINS or "messenger" in url:
        return True
    if is_bad_candidate(product, domain, pages, url):
        return True
    if is_service_listing(product, pages, url):
        return True
    if product in {"unknown", "none"} and landing in {"homepage", "generic", "unknown"}:
        return True
    if product in {"unknown", "none"} and rel < 1:
        return True
    if landing == "homepage" and rel <= 0:
        return True
    return False


def finalize_label(row):
    """Gán nhãn chặt sau khi tính điểm."""
    win_score = numeric(row.get("win_score", 0), 0)
    rel = numeric(row.get("relevance_score", 0), 0)
    evidence = numeric(row.get("evidence_points", 0), 0)
    penalty = numeric(row.get("penalty", 0), 0)
    product = normalize_text(row.get("product", ""))
    landing = row.get("landing_type", "unknown")

    if is_junk_product_row(row):
        return "junk", "low"

    if penalty >= 18 or rel <= -2:
        return "weak", "low"
    if product in {"unknown", "none"}:
        return "watchlist" if win_score >= 20 else "weak", "low"
    if landing != "product" and rel < 2:
        return "watchlist" if win_score >= 22 else "weak", "medium"

    if win_score >= 28 and evidence >= 6 and rel >= 2 and landing == "product":
        return "winner_candidate", "high"
    if win_score >= 22 and evidence >= 5 and rel >= 1:
        return "winner_candidate", "medium"
    if win_score >= 16 and evidence >= 4 and rel >= 0:
        return "watchlist", "medium"
    if win_score >= 10:
        return "testing", "low"
    return "weak", "low"


def apply_smart_filter(rows):
    """Lọc + gán nhãn lại — bỏ junk, xếp hạng lại."""
    kept = []
    for row in rows:
        r = dict(row)
        if is_junk_product_row(r):
            continue
        label, confidence = finalize_label(r)
        r["label"] = label
        r["confidence"] = confidence
        kept.append(r)

    kept.sort(
        key=lambda x: (
            x["label"] == "winner_candidate",
            x["label"] == "watchlist",
            x["win_score"],
            x["relevance_score"],
            x["evidence_points"],
            x["ads_count"],
        ),
        reverse=True,
    )
    return kept


def build_search_url(keyword):
    q = urllib.parse.quote(keyword)
    return f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={COUNTRY}&q={q}"


# =========================
# SCRAPER HELPERS
# =========================
def scroll_ads(page):
    last = 0
    stable_rounds = 0

    for i in range(SCROLL_ROUNDS):
        page.mouse.wheel(0, 800)

        count = last
        for _ in range(10):
            time.sleep(0.5)
            count_en = page.locator("text=Library ID").count()
            count_vi = page.locator("text=ID thư viện").count()
            count = max(count_en, count_vi)
            if count > last:
                break

        debug(f"[DEBUG] scroll {i+1}: last={last}, now={count}")

        if count == last:
            stable_rounds += 1
        else:
            stable_rounds = 0

        if stable_rounds >= 4:
            break

        last = count


def locate_cards(page):
    selectors = [
        "xpath=//*[contains(text(),'Library ID')]/ancestor::div[7]",
        "xpath=//*[contains(text(),'ID thư viện')]/ancestor::div[7]",
    ]

    best = None
    best_count = 0

    for sel in selectors:
        try:
            loc = page.locator(sel)
            cnt = loc.count()
            debug(f"[DEBUG] locate_cards: {sel} => {cnt}")
            if cnt > best_count:
                best = loc
                best_count = cnt
        except Exception as e:
            debug(f"[DEBUG] locate_cards error: {sel} -> {e}")

    return best if best_count else None


def get_card_text(card):
    try:
        return card.inner_text(timeout=5000)
    except Exception:
        return ""


def extract_ad_id(text):
    patterns = [r"ID thư viện:?\s*(\d+)", r"Library ID:?\s*(\d+)"]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)
    return None


def extract_page_name(card):
    try:
        links = card.locator("a[href*='facebook.com/']").all()
        for a in links:
            try:
                href = a.get_attribute("href") or ""
                txt = (a.inner_text() or "").strip()
                if not txt:
                    continue
                if "facebook.com/" in href and len(txt) <= 80:
                    if txt.lower() not in {"xem chi tiết quảng cáo", "mở menu thả xuống", "see ad details"}:
                        return txt
            except Exception:
                pass
    except Exception:
        pass

    try:
        img = card.locator("img[alt]").first
        if img.count() > 0:
            alt = img.get_attribute("alt")
            if alt:
                return alt.strip()
    except Exception:
        pass

    return "unknown"


def extract_landing_link(card):
    try:
        links = card.locator("a[href]").all()
    except Exception:
        links = []

    candidates = []
    for a in links:
        try:
            href = a.get_attribute("href")
            if not href:
                continue
            real = decode_facebook_redirect(href)
            if not real or "facebook.com" in real:
                continue
            candidates.append(real)
        except Exception:
            pass

    if not candidates:
        return None

    candidates = sorted(
        list(set(candidates)),
        key=lambda x: len((urllib.parse.urlparse(x).path or "")),
        reverse=True,
    )
    return candidates[0]


def extract_media_url(card):
    selectors = [
        "video[src]",
        "video[poster]",
        "img[src]",
    ]
    for selector in selectors:
        try:
            nodes = card.locator(selector).all()
        except Exception:
            nodes = []
        for node in nodes:
            try:
                for attr in ("src", "poster"):
                    value = node.get_attribute(attr)
                    if value and value.startswith("http"):
                        return value
            except Exception:
                pass
    return ""


def scrape_ads(page, keyword, search_url):
    cards = locate_cards(page)
    if not cards:
        debug(f"[DEBUG] {keyword}: locate_cards() -> no cards")
        return []

    total = cards.count()
    debug(f"[DEBUG] {keyword}: cards.count() = {total}")

    ads_data = []
    seen_ids = set()

    for i in range(total):
        try:
            card = cards.nth(i)
            text = get_card_text(card)
            if not text:
                continue

            ad_id = extract_ad_id(text)
            if not ad_id or ad_id in seen_ids:
                continue
            seen_ids.add(ad_id)

            page_name = extract_page_name(card)
            landing = extract_landing_link(card)
            media_url = extract_media_url(card)
            info = extract_info_from_url(landing)
            days = parse_start_days(text)
            ad_copy = strip_noise_from_raw_text(text)[:800]
            mtype = "video" if ad_has_video_media({"media_url": media_url}) else ("image" if media_url else "none")

            ads_data.append({
                "keyword": keyword,
                "search_url": search_url,
                "id": ad_id,
                "page": page_name,
                "landing_url": landing or "",
                "clean_url": info["clean_url"],
                "domain": info["domain"],
                "slug": info["slug"],
                "product": info["product"],
                "landing_type": info["landing_type"],
                "days": days,
                "raw_text": text,
                "ad_copy": ad_copy,
                "media_url": media_url,
                "media_type": mtype,
                "country": COUNTRY,
            })
        except Exception as e:
            debug(f"[DEBUG] exception on card {i}: {e}")

    debug(f"[DEBUG] {keyword}: final ads_data = {len(ads_data)}")
    return ads_data


# =========================
# WINNER SCORER
# =========================
def tokenize_signature(text):
    text = normalize_text(text).replace("_", " ").replace("-", " ")
    tokens = [t for t in text.split() if len(t) >= 3 and t not in SIGNATURE_STOPWORDS and not t.isdigit()]
    return tokens


def strip_noise_from_raw_text(raw_text):
    text = raw_text or ""
    patterns = [
        r"Library ID:?\s*\d+",
        r"ID thư viện:?\s*\d+",
        r"Started running on[^\n]*",
        r"Ngày bắt đầu chạy:?[^\n]*",
        r"See ad details",
        r"Xem chi tiết quảng cáo",
        r"Low impressions",
        r"Ít lượt hiển thị",
    ]
    for pattern in patterns:
        text = re.sub(pattern, " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def pick_display_name(ad):
    candidates = [ad.get("product", ""), slug_to_name(ad.get("slug", ""))]
    for item in candidates:
        item = normalize_text(item)
        if item and item not in {"unknown", "none"}:
            return item
    return "unknown"


def build_product_signature(ad):
    domain = normalize_domain(ad.get("domain", "unknown"))
    page = normalize_text(ad.get("page", ""))
    product = normalize_text(ad.get("product", ""))
    slug = normalize_text(ad.get("slug", ""))
    clean_landing = clean_landing_url(ad.get("clean_url", "") or ad.get("landing_url", ""))

    seed_parts = [product, slug]
    tokens = []
    for part in seed_parts:
        tokens.extend(tokenize_signature(part))

    domain_tokens = set(tokenize_signature(domain.replace(".", " ")))
    page_tokens = set(tokenize_signature(page))
    filtered = [t for t in tokens if t not in domain_tokens and t not in page_tokens]
    if not filtered:
        filtered = tokens[:]

    filtered = sorted(set(filtered), key=lambda t: (t in FREQUENCY_TOKEN_BLACKLIST, t))
    if filtered:
        return " ".join(filtered[:5])

    parsed = extract_info_from_url(clean_landing)
    fallback = normalize_text(parsed.get("product", ""))
    if fallback and fallback not in {"unknown", "none"}:
        return fallback

    return f"domain:{domain}"


def build_creative_fingerprint(ad):
    raw_text = strip_noise_from_raw_text(ad.get("raw_text", "") or ad.get("ad_copy", ""))
    media_url = ad.get("media_url", "")
    clean_landing = clean_landing_url(ad.get("clean_url", "") or ad.get("landing_url", ""))
    page = normalize_text(ad.get("page", ""))
    keyword = normalize_text(ad.get("keyword", ""))

    if raw_text or media_url:
        seed = " | ".join([raw_text[:500], media_url, clean_landing])
    else:
        seed = " | ".join([clean_landing, keyword, page])
    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]


def has_true_creative_signal(ads):
    for ad in ads:
        if ad.get("raw_text") or ad.get("ad_copy") or ad.get("media_url"):
            return True
    return False


def ad_has_video_media(ad: dict) -> bool:
    u = (ad.get("media_url") or "").lower()
    if not u:
        return False
    return "video" in u or ".mp4" in u or ".webm" in u or ".m3u8" in u


def primary_media_for_ads(ads: list) -> str:
    if not ads:
        return "unknown"
    video_n = sum(1 for a in ads if ad_has_video_media(a))
    with_media = sum(1 for a in ads if (a.get("media_url") or "").strip())
    img_n = max(with_media - video_n, 0)
    n = len(ads)
    if video_n >= max(1, n * 0.45):
        return "video"
    if img_n >= max(1, n * 0.45):
        return "image"
    if video_n and img_n:
        return "mixed"
    return "unknown"


def score_threshold_points(value, thresholds):
    score = 0
    for threshold, points in thresholds:
        if value >= threshold:
            score += points
    return score


def score_group(ads, signature):
    sample = ads[0]
    pages = sorted({a.get("page", "") for a in ads if a.get("page") and a.get("page") != "unknown"})
    keywords = sorted({a.get("keyword", "") for a in ads if a.get("keyword")})
    urls = sorted({clean_landing_url(a.get("clean_url", "") or a.get("landing_url", "")) for a in ads if a.get("clean_url") or a.get("landing_url")})
    domains = sorted({normalize_domain(a.get("domain", "unknown")) for a in ads if a.get("domain") and a.get("domain") != "unknown"})
    creatives = sorted({a.get("creative_fingerprint", "") for a in ads if a.get("creative_fingerprint")})

    ads_count = len(ads)
    pages_count = len(pages)
    keywords_count = len(keywords)
    urls_count = len(urls)
    domain_count = len(domains)
    creative_count = len(creatives)

    day_values = sorted(max(numeric(a.get("days", 0), 0), 0) for a in ads)
    max_days = max(day_values) if day_values else 0
    median_days = int(statistics.median(day_values)) if day_values else 0
    ads_7d_plus = sum(1 for d in day_values if d >= 7)
    ads_14d_plus = sum(1 for d in day_values if d >= 14)
    ads_30d_plus = sum(1 for d in day_values if d >= 30)

    page_freq = Counter(a.get("page", "") for a in ads if a.get("page"))
    repeat_page_count = sum(1 for _, cnt in page_freq.items() if cnt >= 2)

    name_counter = Counter(pick_display_name(ad) for ad in ads)
    product_name = name_counter.most_common(1)[0][0] if name_counter else "unknown"
    slug = normalize_text(sample.get("slug", ""))
    landing_type = sample.get("landing_type", "unknown")
    sample_url = urls[0] if urls else clean_landing_url(sample.get("clean_url", "") or sample.get("landing_url", ""))
    sample_domain = domains[0] if domains else normalize_domain(sample.get("domain", "unknown"))
    primary_media = primary_media_for_ads(ads)
    video_ads = sum(1 for a in ads if ad_has_video_media(a))
    try:
        from winnerspy_filters import _is_shopify

        is_shopify = _is_shopify(sample_domain, sample_url)
    except ImportError:
        is_shopify = "myshopify" in sample_domain or "shopify" in sample_url.lower()

    reasons = []

    ads_signal = score_threshold_points(ads_count, [(2, 1), (3, 2), (5, 3), (10, 4), (20, 5)])
    if ads_signal:
        reasons.append(f"ads_signal={ads_signal} from {ads_count} ads")

    durability_signal = 0
    durability_signal += score_threshold_points(max_days, [(3, 1), (7, 2), (14, 3), (30, 4), (90, 5)])
    durability_signal += score_threshold_points(median_days, [(3, 1), (7, 2), (14, 3)])
    durability_signal += score_threshold_points(ads_14d_plus, [(2, 1), (4, 2)])
    if durability_signal:
        reasons.append(f"durability_signal={durability_signal} (max_days={max_days}, median_days={median_days})")

    page_signal = 0
    page_signal += score_threshold_points(pages_count, [(2, 2), (3, 3), (5, 4)])
    page_signal += score_threshold_points(repeat_page_count, [(2, 1), (3, 2)])
    if page_signal:
        reasons.append(f"page_signal={page_signal} from {pages_count} pages")

    creative_signal = 0
    creative_signal += score_threshold_points(creative_count, [(2, 2), (3, 3), (5, 4), (8, 5)])
    creative_ratio = (creative_count / ads_count) if ads_count else 0.0
    if creative_ratio >= 0.35:
        creative_signal += 2
    if creative_ratio >= 0.55:
        creative_signal += 2
    if creative_signal:
        reasons.append(f"creative_signal={creative_signal} from {creative_count} creative variants")

    demand_proxy_signal = 0
    demand_proxy_signal += score_threshold_points(keywords_count, [(2, 2), (3, 3), (5, 4)])
    demand_proxy_signal += score_threshold_points(domain_count, [(2, 2), (3, 3)])
    demand_proxy_signal += score_threshold_points(urls_count, [(2, 1), (3, 2), (5, 3)])
    if landing_type == "product":
        demand_proxy_signal += 2
    elif landing_type in {"generic", "homepage"}:
        demand_proxy_signal -= 2
    rel = relevance_score(product_name, slug, " ".join(domains), sample_url)
    demand_proxy_signal += rel
    if demand_proxy_signal:
        reasons.append(f"demand_proxy_signal={demand_proxy_signal}")

    penalty = 0
    if any(d in BAD_DOMAINS for d in domains):
        penalty += 5
        reasons.append("penalty: marketplace/social domain")
    if is_low_quality_product(normalize_domain(sample.get("domain", "unknown")), slug, product_name, sample_url):
        penalty += 12
        reasons.append("penalty: low-quality slug/domain")
    if is_bad_candidate(product_name, normalize_domain(sample.get("domain", "unknown")), pages, sample_url):
        penalty += 20
        reasons.append("penalty: likely non-physical/content candidate")
    raw_snips = [strip_noise_from_raw_text(a.get("raw_text", ""))[:200] for a in ads[:5]]
    if is_service_listing(product_name, pages, sample_url, raw_snips):
        penalty += 22
        reasons.append("penalty: service/local business not physical product")
    if product_name in {"unknown", "none"}:
        penalty += 10
        reasons.append("penalty: unknown product name")
    if landing_type in {"homepage", "generic"}:
        penalty += 8
        reasons.append("penalty: not product landing page")
    if rel < 0:
        penalty += abs(rel) * 2
        reasons.append("penalty: low niche relevance")
    low_impression_count = sum(1 for a in ads if has_low_impression(a.get("raw_text", "")))
    if low_impression_count >= 1:
        penalty += 3
        reasons.append("penalty: has low-impression ads")
    if low_impression_count >= 3:
        penalty += 2
        reasons.append("penalty: many low-impression ads")

    win_score = ads_signal + durability_signal + page_signal + creative_signal + demand_proxy_signal - penalty

    evidence_points = sum([
        ads_count >= 5,
        max_days >= 14,
        median_days >= 7,
        pages_count >= 2,
        creative_count >= 2,
        keywords_count >= 2,
        domain_count >= 2,
        landing_type == "product",
        rel > 0,
    ])

    row_preview = {
        "product": product_name,
        "sample_domain": normalize_domain(sample.get("domain", "unknown")),
        "sample_url": sample_url,
        "landing_type": landing_type,
        "pages": pages,
        "ads_count": ads_count,
        "win_score": win_score,
        "relevance_score": rel,
        "evidence_points": evidence_points,
        "penalty": penalty,
        "reasons": reasons,
    }
    label, confidence = finalize_label(row_preview)

    return {
        "signature": signature,
        "product": product_name,
        "sample_domain": normalize_domain(sample.get("domain", "unknown")),
        "sample_slug": slug,
        "sample_url": sample_url,
        "ads_count": ads_count,
        "pages_count": pages_count,
        "pages": pages,
        "repeat_page_count": repeat_page_count,
        "keywords_count": keywords_count,
        "keywords": keywords,
        "urls_count": urls_count,
        "domain_count": domain_count,
        "domains": domains,
        "creative_count": creative_count,
        "creative_ratio": round(creative_ratio, 3),
        "has_true_creative_signal": has_true_creative_signal(ads),
        "max_days": max_days,
        "median_days": median_days,
        "ads_7d_plus": ads_7d_plus,
        "ads_14d_plus": ads_14d_plus,
        "ads_30d_plus": ads_30d_plus,
        "landing_type": landing_type,
        "ads_signal": ads_signal,
        "durability_signal": durability_signal,
        "page_signal": page_signal,
        "creative_signal": creative_signal,
        "demand_proxy_signal": demand_proxy_signal,
        "penalty": penalty,
        "relevance_score": rel,
        "low_impression_count": low_impression_count,
        "evidence_points": evidence_points,
        "win_score": win_score,
        "label": label,
        "confidence": confidence,
        "reasons": reasons,
        "ad_ids": [a.get("id", "") for a in ads][:20],
        "primary_media": primary_media,
        "video_ads": video_ads,
        "is_shopify": is_shopify,
    }


def rank_products_scored(all_ads):
    """Chấm điểm + smart filter — chưa áp preset AdSpy (luôn có dữ liệu nếu raw có ads)."""
    grouped = defaultdict(list)
    for ad in all_ads:
        signature = build_product_signature(ad)
        ad["product_signature"] = signature
        ad["creative_fingerprint"] = build_creative_fingerprint(ad)
        grouped[signature].append(ad)

    ranked = [score_group(ads, signature) for signature, ads in grouped.items()]
    ranked.sort(
        key=lambda x: (
            x["win_score"],
            x["confidence"] == "high",
            x["evidence_points"],
            x["creative_count"],
            x["pages_count"],
            x["domain_count"],
            x["ads_count"],
            x["max_days"],
        ),
        reverse=True,
    )
    return apply_smart_filter(ranked)


def filter_scored_rows(scored, filter_preset: str = "balanced", filter_overrides: dict | None = None):
    try:
        from winnerspy_filters import apply_product_filters, normalize_filter_preset

        return apply_product_filters(
            scored,
            normalize_filter_preset(filter_preset),
            filter_overrides,
        )
    except ImportError:
        return list(scored)


def rank_products(all_ads, filter_preset: str = "balanced", filter_overrides: dict | None = None):
    """Chỉ trả SP đạt preset — dùng rank_products_pipeline nếu cần cả scored."""
    scored = rank_products_scored(all_ads)
    return filter_scored_rows(scored, filter_preset, filter_overrides)


def rank_products_pipeline(all_ads, filter_preset: str = "balanced", filter_overrides: dict | None = None):
    """Trả (scored, winners) — scored luôn lưu; winners = sau preset (có thể rỗng)."""
    scored = rank_products_scored(all_ads)
    winners = filter_scored_rows(scored, filter_preset, filter_overrides)
    return scored, winners


def mark_preset_matches(scored: list[dict], winners: list[dict]) -> list[dict]:
    ok = {(w.get("signature") or "").strip() for w in winners}
    out = []
    for row in scored:
        r = dict(row)
        r["matches_preset"] = "1" if (r.get("signature") or "").strip() in ok else "0"
        out.append(r)
    return out


def pool_for_tiktok(winners: list[dict], scored: list[dict], limit: int) -> list[dict]:
    """TikTok/Trends: ưu tiên SP đạt preset; nếu trống → top watchlist/winner đã chấm điểm."""
    if winners:
        return winners[: max(1, int(limit))]
    labels = {"winner_candidate", "watchlist"}
    fallback = [r for r in scored if (r.get("label") or "") in labels]
    return fallback[: max(1, int(limit))]


def print_pipeline_summary(raw_count: int, scored: list, winners: list, preset: str) -> None:
    print("\n" + "-" * 60)
    print("DATA SUMMARY")
    print("-" * 60)
    print(f"  Facebook ads (raw):           {raw_count}")
    print(f"  Scored products:              {len(scored)}  -> scored_products.csv")
    print(f"  Products matching '{preset}': {len(winners)}  -> winner_products.csv")
    if not winners and scored:
        print(
            "  → Preset matched nothing but data exists — see scored + Ad library; "
            "TikTok runs on top watchlist if enabled."
        )
    print("-" * 60)


# =========================
# CSV IO
# =========================
def dedupe_ads_by_id(all_ads):
    dedup = {}
    anonymous = []
    for ad in all_ads:
        ad_id = ad.get("id")
        if ad_id:
            dedup[ad_id] = ad
        else:
            anonymous.append(ad)
    return list(dedup.values()) + anonymous


def save_raw_ads_csv(all_ads, filepath="raw_ads.csv"):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "keyword", "search_url", "id", "page", "domain", "slug", "product",
                "landing_type", "landing_url", "clean_url", "days", "raw_text", "ad_copy",
                "media_url", "media_type", "country",
            ],
        )
        writer.writeheader()
        for ad in all_ads:
            writer.writerow({
                "keyword": ad.get("keyword", ""),
                "search_url": ad.get("search_url", ""),
                "id": ad.get("id", ""),
                "page": ad.get("page", ""),
                "domain": ad.get("domain", "unknown"),
                "slug": ad.get("slug", "none"),
                "product": ad.get("product", "unknown"),
                "landing_type": ad.get("landing_type", "unknown"),
                "landing_url": ad.get("landing_url", ""),
                "clean_url": ad.get("clean_url", ""),
                "days": ad.get("days", 0),
                "raw_text": ad.get("raw_text", ""),
                "ad_copy": ad.get("ad_copy", ""),
                "media_url": ad.get("media_url", ""),
                "media_type": ad.get("media_type", ""),
                "country": ad.get("country", COUNTRY),
            })


PRODUCT_CSV_FIELDS = [
    "rank", "win_score", "label", "confidence", "evidence_points", "matches_preset",
    "product", "signature", "sample_domain", "sample_slug", "sample_url",
    "ads_count", "pages_count", "repeat_page_count", "keywords_count",
    "urls_count", "domain_count", "creative_count", "creative_ratio",
    "has_true_creative_signal", "max_days", "median_days", "ads_7d_plus",
    "ads_14d_plus", "ads_30d_plus", "landing_type", "ads_signal",
    "durability_signal", "page_signal", "creative_signal",
    "demand_proxy_signal", "penalty", "relevance_score", "low_impression_count",
    "domains", "pages", "keywords", "ad_ids", "reasons",
]


def _csv_join_field(row: dict, key: str) -> str:
    val = row.get(key, "")
    if isinstance(val, (list, tuple, set)):
        if key == "ad_ids":
            return ",".join(str(x) for x in val)
        return " | ".join(str(x) for x in val)
    return val if val is not None else ""


def _product_row_for_csv(idx: int, row: dict) -> dict:
    return {
        "rank": idx,
        "win_score": row["win_score"],
        "label": row["label"],
        "confidence": row["confidence"],
        "evidence_points": row["evidence_points"],
        "matches_preset": row.get("matches_preset", ""),
        "product": row["product"],
        "signature": row["signature"],
        "sample_domain": row["sample_domain"],
        "sample_slug": row["sample_slug"],
        "sample_url": row["sample_url"],
        "ads_count": row["ads_count"],
        "pages_count": row["pages_count"],
        "repeat_page_count": row["repeat_page_count"],
        "keywords_count": row["keywords_count"],
        "urls_count": row["urls_count"],
        "domain_count": row["domain_count"],
        "creative_count": row["creative_count"],
        "creative_ratio": row["creative_ratio"],
        "has_true_creative_signal": row["has_true_creative_signal"],
        "max_days": row["max_days"],
        "median_days": row["median_days"],
        "ads_7d_plus": row["ads_7d_plus"],
        "ads_14d_plus": row["ads_14d_plus"],
        "ads_30d_plus": row["ads_30d_plus"],
        "landing_type": row["landing_type"],
        "ads_signal": row["ads_signal"],
        "durability_signal": row["durability_signal"],
        "page_signal": row["page_signal"],
        "creative_signal": row["creative_signal"],
        "demand_proxy_signal": row["demand_proxy_signal"],
        "penalty": row["penalty"],
        "relevance_score": row["relevance_score"],
        "low_impression_count": row["low_impression_count"],
        "domains": _csv_join_field(row, "domains"),
        "pages": _csv_join_field(row, "pages"),
        "keywords": _csv_join_field(row, "keywords"),
        "ad_ids": _csv_join_field(row, "ad_ids"),
        "reasons": _csv_join_field(row, "reasons"),
    }


def save_winners_csv(rows, filepath="winner_products.csv"):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=PRODUCT_CSV_FIELDS,
        )
        writer.writeheader()
        for idx, row in enumerate(rows, start=1):
            writer.writerow(_product_row_for_csv(idx, row))


def save_scored_csv(rows, filepath="scored_products.csv"):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=PRODUCT_CSV_FIELDS)
        writer.writeheader()
        for idx, row in enumerate(rows, start=1):
            writer.writerow(_product_row_for_csv(idx, row))


def save_filter_summary(filepath, summary: dict) -> None:
    import json

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def load_raw_ads_csv(filepath):
    with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    ads = []
    for row in rows:
        landing_url = row.get("landing_url", "")
        clean_url = row.get("clean_url", "")
        domain = normalize_domain(row.get("domain", ""))
        slug = normalize_text(row.get("slug", "")) or "none"
        product = normalize_text(row.get("product", "")) or "unknown"
        landing_type = row.get("landing_type", "unknown")

        if (not clean_url or domain in {"", "unknown"}) and landing_url:
            info = extract_info_from_url(landing_url)
            clean_url = info["clean_url"]
            domain = info["domain"]
            slug = info["slug"]
            product = info["product"]
            landing_type = info["landing_type"]

        ads.append({
            "keyword": row.get("keyword", ""),
            "search_url": row.get("search_url", build_search_url(row.get("keyword", ""))) if row.get("keyword") else row.get("search_url", ""),
            "id": row.get("id", ""),
            "page": row.get("page", ""),
            "landing_url": landing_url,
            "clean_url": clean_url,
            "domain": domain,
            "slug": slug,
            "product": product,
            "landing_type": landing_type,
            "days": numeric(row.get("days", 0), 0),
            "raw_text": row.get("raw_text", ""),
            "media_url": row.get("media_url", ""),
        })
    return ads


# =========================
# RUNNERS
# =========================
def print_top_winners(rows, top_n=TOP_N):
    print("\n" + "=" * 90)
    print("TOP WINNING PRODUCT CANDIDATES")
    print("=" * 90)
    if not rows:
        print("No data.")
        return

    for idx, row in enumerate(rows[:top_n], start=1):
        print(f"\n#{idx} {row['product']}")
        print(f"signature      : {row['signature']}")
        print(f"win_score      : {row['win_score']} ({row['label']}, {row['confidence']})")
        print(f"ads            : {row['ads_count']}")
        print(f"pages          : {row['pages_count']} | repeat_pages={row['repeat_page_count']}")
        print(f"creative_count : {row['creative_count']} | ratio={row['creative_ratio']}")
        print(f"domains        : {row['domain_count']} | keywords={row['keywords_count']}")
        print(f"days           : max={row['max_days']} median={row['median_days']}")
        print(f"sample_url     : {row['sample_url'] or 'none'}")
        print(f"reasons        : {'; '.join(row['reasons'])}")


def _default_scored_path(winners_csv_path: str) -> str:
    return str(Path(winners_csv_path).parent / "scored_products.csv")


def persist_scored_and_winners(
    all_ads,
    winners_csv_path: str,
    scored_csv_path: str | None,
    filter_preset: str,
    filter_overrides: dict | None,
):
    """Lưu 2 tầng: scored (đã chấm) + winners (đạt preset)."""
    scored_out = scored_csv_path or _default_scored_path(winners_csv_path)
    scored, winners = rank_products_pipeline(all_ads, filter_preset, filter_overrides)
    scored_marked = mark_preset_matches(scored, winners)
    save_scored_csv(scored_marked, scored_out)
    save_winners_csv(winners, winners_csv_path)
    summary_path = str(Path(winners_csv_path).parent / "filter_summary.json")
    save_filter_summary(
        summary_path,
        {
            "preset": filter_preset,
            "raw_ads": len(all_ads),
            "scored_products": len(scored),
            "matches_preset": len(winners),
            "overrides": filter_overrides or {},
        },
    )
    print_pipeline_summary(len(all_ads), scored, winners, filter_preset)
    print_top_winners(winners if winners else scored_marked, TOP_N)
    if not winners and scored_marked:
        print("\n(Tip) Top list = scored_products.csv — matches_preset=1 means preset match.")
    return scored_marked, winners, scored_out


def rebuild_winners_from_raw(
    raw_csv_path,
    winners_csv_path,
    filter_preset="balanced",
    filter_overrides=None,
    scored_csv_path=None,
):
    all_ads = dedupe_ads_by_id(load_raw_ads_csv(raw_csv_path))
    scored, winners, _ = persist_scored_and_winners(
        all_ads, winners_csv_path, scored_csv_path, filter_preset, filter_overrides
    )
    return all_ads, scored, winners


def run(
    scrape=True,
    raw_out="raw_ads.csv",
    winners_out="winner_products.csv",
    scored_out=None,
    links_out="search_links.txt",
    raw_in=None,
    run_tiktok=False,
    tiktok_out="final_research_results.csv",
    tiktok_limit=15,
    run_google_trends=False,
    gt_limit=15,
    report_out=None,
    filter_preset="balanced",
    filter_overrides=None,
):
    report_source = winners_out
    scored_out = scored_out or _default_scored_path(winners_out)
    filter_preset = filter_preset or "balanced"
    filter_overrides = filter_overrides or {}

    def _enrichment_steps(scored, winners):
        nonlocal report_source
        enrich_pool = pool_for_tiktok(winners, scored, tiktok_limit)
        if run_tiktok and enrich_pool:
            if winners:
                out = run_tiktok_validator(winners_out, tiktok_out, limit=tiktok_limit)
            else:
                print("\n[TikTok] winner_products.csv trong — check top watchlist tu scored.")
                out = run_tiktok_validator(
                    None, tiktok_out, limit=tiktok_limit, pool_rows=enrich_pool
                )
            if out:
                report_source = out
        if run_google_trends and enrich_pool:
            gt_in = report_source if os.path.isfile(report_source) else winners_out
            if not os.path.isfile(gt_in) and scored_out and os.path.isfile(scored_out):
                gt_in = scored_out
            out = run_google_trends_enrich(gt_in, tiktok_out, limit=gt_limit, geo=COUNTRY)
            if out:
                report_source = out

    if not scrape:
        if not raw_in:
            raise ValueError("raw_in is required when scrape=False")
        all_ads, scored, winners = rebuild_winners_from_raw(
            raw_in,
            winners_out,
            filter_preset=filter_preset,
            filter_overrides=filter_overrides,
            scored_csv_path=scored_out,
        )
        print(f"Rebuilt from: {raw_in}")
        print(f"Saved: {scored_out}, {winners_out}")
        _enrichment_steps(scored, winners)
        if report_out:
            export_html_report(
                html_path=report_out,
                job_dir=Path(report_out).parent,
                subtitle_extra="" if winners else "0 preset matches — showing top scored list",
            )
        return

    all_ads = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            err = str(e)
            if "ECONNREFUSED" in err or "refused" in err.lower():
                print(
                    "\n[ERROR] Cannot connect to Chrome at", CDP_URL,
                    "\n  → Run start_chrome_debug.bat, log into Facebook, keep Chrome open, then scan again.",
                    sep="\n",
                )
            raise
        context = browser.contexts[0] if browser.contexts else browser.new_context()

        page = context.new_page()
        page.goto("https://www.facebook.com/ads/library/")
        print(page.title())
        page.close()

        with open(links_out, "w", encoding="utf-8") as link_file:
            for idx, keyword in enumerate(KEYWORDS, start=1):
                print(f"\n[{idx}/{len(KEYWORDS)}] Searching keyword: {keyword}")
                page = context.new_page()
                try:
                    url = build_search_url(keyword)
                    print("SEARCH URL:", url)
                    link_file.write(f"{keyword} -> {url}\n")

                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    time.sleep(7)

                    scroll_ads(page)
                    ads = scrape_ads(page, keyword, url)
                    print(f"  -> scraped {len(ads)} ads")
                    all_ads.extend(ads)
                except Exception as e:
                    print(f"  -> error on keyword '{keyword}': {e}")
                finally:
                    page.close()

        all_ads = dedupe_ads_by_id(all_ads)
        print(f"\nTotal unique ads scraped: {len(all_ads)}")

        save_raw_ads_csv(all_ads, raw_out)
        scored, winners, _ = persist_scored_and_winners(
            all_ads, winners_out, scored_out, filter_preset, filter_overrides
        )

        print("\nSaved:")
        print(f"- {links_out}")
        print(f"- {raw_out}")
        print(f"- {scored_out}")
        print(f"- {winners_out}")
        if winners and not winners[0]["has_true_creative_signal"]:
            print("\nNote: creative_count is using a fallback proxy because raw creative fields are missing.")
            print("For better accuracy, raw_text and media_url are now saved into raw_ads.csv for future rebuilds.")

        if not USE_CDP:
            browser.close()

    if scrape:
        _enrichment_steps(scored, winners)

    if report_out:
        export_html_report(
            html_path=report_out,
            job_dir=Path(report_out).parent,
            subtitle_extra="" if winners else "0 preset matches — showing top scored list",
        )


def load_keywords_arg(value):
    if not value:
        return None
    if value in KEYWORD_PRESETS:
        return list(KEYWORD_PRESETS[value])
    path = value
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            keywords = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    else:
        keywords = [k.strip() for k in value.replace("\n", ",").split(",") if k.strip()]
    return keywords


def parse_args():
    parser = argparse.ArgumentParser(
        description="WinnerSpy: Facebook Ads Library research + winner score + TikTok check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  chrome --remote-debugging-port=9222
  python r.py --preset cleaning_us --report report.html
  python r.py --from-raw raw_ads.csv --tiktok --report report.html
  python r.py --country US --keywords "mop,cleaning brush" --scroll 10
        """,
    )
    parser.add_argument("--from-raw", dest="raw_in", help="Re-score from raw_ads.csv only (no scrape)")
    parser.add_argument("--raw-out", default="raw_ads.csv", help="Raw ads CSV")
    parser.add_argument("--winners-out", default="winner_products.csv", help="Winner CSV (preset matches)")
    parser.add_argument("--scored-out", default=None, help="All scored products CSV")
    parser.add_argument("--links-out", default="search_links.txt", help="Search URL log file")
    parser.add_argument("--final-out", default="final_research_results.csv", help="CSV after TikTok")
    parser.add_argument("--report", dest="report_out", default=None, help="Export HTML report")
    parser.add_argument("--country", default=None, help="Ads Library country code: US, VN, ALL, ...")
    parser.add_argument(
        "--keywords",
        default=None,
        help="Preset (cleaning_us, cleaning_vn, home_gadget_us), .txt file, or comma-separated keywords",
    )
    parser.add_argument("--preset", default=None, help="Alias: cleaning_us | cleaning_vn | home_gadget_us")
    parser.add_argument("--scroll", type=int, default=None, help="Scroll rounds (default 8)")
    parser.add_argument("--top", type=int, default=None, help="Print top N winners (default 20)")
    parser.add_argument("--tiktok", action="store_true", help="Check TikTok for top winners (needs Chrome CDP)")
    parser.add_argument("--tiktok-limit", type=int, default=15, help="Max products for TikTok check (default 15)")
    parser.add_argument("--google-trends", action="store_true", help="Google Trends (VIP, needs pytrends)")
    parser.add_argument("--gt-limit", type=int, default=15, help="Max products for Google Trends")
    parser.add_argument("--cdp", default=None, help="CDP URL (default http://127.0.0.1:9222)")
    parser.add_argument(
        "--filter-preset",
        default="balanced",
        help="Smart filter: balanced, strict_winner, scaling, new_test, durable, shopify_dtc",
    )
    parser.add_argument("--filter-media", default="any", help="any | video | image")
    parser.add_argument("--filter-tech", default="any", help="any | shopify")
    parser.add_argument("--filter-min-ads", type=int, default=0, help="Override: minimum ad count")
    parser.add_argument("--filter-min-days", type=int, default=0, help="Override: minimum run days")
    parser.add_argument("--filter-max-days", type=int, default=0, help="Override: maximum run days")
    parser.add_argument("--filter-sort", default="score", help="score | ads | days | creative")
    parser.add_argument("--filter-product-only", action="store_true", help="Product landing pages only")
    parser.add_argument("--filter-no-marketplace", action="store_true", help="Exclude marketplaces")
    parser.add_argument("--debug", action="store_true", help="Verbose logging")
    return parser.parse_args()


def filter_overrides_from_args(args) -> dict:
    over: dict = {}
    if getattr(args, "filter_media", "any") not in ("", "any", None):
        over["media_type"] = args.filter_media
    if getattr(args, "filter_tech", "any") not in ("", "any", None):
        over["tech"] = args.filter_tech
    if getattr(args, "filter_min_ads", 0):
        over["min_ads"] = args.filter_min_ads
    if getattr(args, "filter_min_days", 0):
        over["min_days"] = args.filter_min_days
    if getattr(args, "filter_max_days", 0):
        over["max_days"] = args.filter_max_days
    if getattr(args, "filter_sort", ""):
        over["sort_by"] = args.filter_sort
    if getattr(args, "filter_product_only", False):
        over["product_only"] = True
    if getattr(args, "filter_no_marketplace", False):
        over["exclude_marketplace"] = True
    return over


if __name__ == "__main__":
    args = parse_args()
    DEBUG = args.debug

    kw = load_keywords_arg(args.keywords or args.preset)
    apply_runtime_config(
        country=args.country,
        keywords=kw,
        scroll_rounds=args.scroll,
        top_n=args.top,
        cdp_url=args.cdp,
    )

    print(f"Country: {COUNTRY} | Keywords: {len(KEYWORDS)} | CDP: {CDP_URL}")

    try:
        from winnerspy_filters import normalize_filter_preset

        filter_preset = normalize_filter_preset(args.filter_preset)
        filter_overrides = filter_overrides_from_args(args)
    except ImportError:
        filter_preset = "balanced"
        filter_overrides = {}
    print(f"Filter preset: {filter_preset} | overrides: {filter_overrides or 'none'}")

    scored_out = args.scored_out or _default_scored_path(args.winners_out)

    if args.raw_in:
        run(
            scrape=False,
            raw_in=args.raw_in,
            winners_out=args.winners_out,
            scored_out=scored_out,
            run_tiktok=args.tiktok,
            tiktok_out=args.final_out,
            tiktok_limit=args.tiktok_limit,
            run_google_trends=args.google_trends,
            gt_limit=args.gt_limit,
            report_out=args.report_out or "report.html",
            filter_preset=filter_preset,
            filter_overrides=filter_overrides,
        )
    else:
        run(
            scrape=True,
            raw_out=args.raw_out,
            winners_out=args.winners_out,
            scored_out=scored_out,
            links_out=args.links_out,
            run_tiktok=args.tiktok,
            tiktok_out=args.final_out,
            tiktok_limit=args.tiktok_limit,
            run_google_trends=args.google_trends,
            gt_limit=args.gt_limit,
            report_out=args.report_out or "report.html",
            filter_preset=filter_preset,
            filter_overrides=filter_overrides,
        )
