"""Product filter presets — AdSpy-style (ads, run days, landing, marketplace)."""
from __future__ import annotations

FILTER_PRESETS: dict[str, dict] = {
    "balanced": {
        "title": "Balanced",
        "hint": "Winners + watchlist, drop junk — default",
        "labels": ("winner_candidate", "watchlist"),
        "min_ads": 2,
        "min_days": 0,
        "min_win_score": 0,
        "min_creative": 0,
        "max_days": 0,
        "product_only": False,
        "exclude_marketplace": False,
        "confidence": (),
    },
    "strict_winner": {
        "title": "Strict winner",
        "hint": "≥5 ads, ≥14 days, high score — broad keywords may yield 0; use Balanced",
        "labels": ("winner_candidate",),
        "min_ads": 5,
        "min_days": 14,
        "min_win_score": 22,
        "min_creative": 0,
        "max_days": 0,
        "product_only": True,
        "exclude_marketplace": True,
        "confidence": ("high", "medium"),
    },
    "scaling": {
        "title": "Scaling",
        "hint": "Shops spending hard: 10+ ads or durable campaigns",
        "labels": ("winner_candidate", "watchlist"),
        "min_ads": 10,
        "min_days": 7,
        "min_win_score": 18,
        "min_creative": 0,
        "max_days": 0,
        "product_only": True,
        "exclude_marketplace": True,
        "confidence": (),
    },
    "new_test": {
        "title": "New / testing",
        "hint": "Few ads but many creatives — catch trends early",
        "labels": ("winner_candidate", "watchlist", "testing"),
        "min_ads": 2,
        "min_days": 0,
        "min_win_score": 12,
        "min_creative": 2,
        "max_days": 21,
        "product_only": False,
        "exclude_marketplace": False,
        "confidence": (),
    },
    "durable": {
        "title": "Durable campaigns",
        "hint": "Running 30+ days — past initial test phase",
        "labels": ("winner_candidate", "watchlist"),
        "min_ads": 3,
        "min_days": 30,
        "min_win_score": 16,
        "min_creative": 0,
        "max_days": 0,
        "product_only": True,
        "exclude_marketplace": False,
        "confidence": (),
    },
    "shopify_dtc": {
        "title": "DTC / own store",
        "hint": "Product landing pages, skip Amazon/Shopee marketplaces",
        "labels": ("winner_candidate", "watchlist", "testing"),
        "min_ads": 2,
        "min_days": 0,
        "min_win_score": 10,
        "min_creative": 0,
        "max_days": 0,
        "product_only": True,
        "exclude_marketplace": True,
        "confidence": (),
    },
}

MARKETPLACE_MARKERS = (
    "amazon.",
    "amzn.",
    "aliexpress.",
    "temu.com",
    "wish.",
    "ebay.",
    "tiktok.com/shop",
    "shopee.",
    "lazada.",
    "facebook.com",
    "instagram.com",
)

SHOPIFY_MARKERS = (
    "myshopify.com",
    "shopify.com",
    "cdn.shopify",
    ".myshopify.",
)


def normalize_filter_preset(preset: str | None) -> str:
    p = (preset or "balanced").strip().lower()
    return p if p in FILTER_PRESETS else "balanced"


def preset_meta(preset_id: str) -> dict:
    pid = normalize_filter_preset(preset_id)
    row = dict(FILTER_PRESETS[pid])
    row["id"] = pid
    return row


def list_presets_for_ui() -> list[dict]:
    out = []
    for pid, cfg in FILTER_PRESETS.items():
        out.append({"id": pid, **cfg})
    return out


def parse_web_filter_opts(opts: dict) -> dict:
    """Web form → overrides for apply_product_filters."""
    over: dict = {}
    media = (opts.get("filter_media") or "any").strip().lower()
    tech = (opts.get("filter_tech") or "any").strip().lower()
    if media in ("video", "image"):
        over["media_type"] = media
    if tech == "shopify":
        over["tech"] = "shopify"
    for src, dst in (
        ("filter_min_ads", "min_ads"),
        ("filter_min_days", "min_days"),
        ("filter_max_days", "max_days"),
    ):
        raw = (opts.get(src) or "").strip()
        if raw.isdigit():
            over[dst] = int(raw)
    sort_by = (opts.get("filter_sort") or "").strip()
    if sort_by:
        over["sort_by"] = sort_by
    if opts.get("filter_product_only"):
        over["product_only"] = True
    if opts.get("filter_no_marketplace"):
        over["exclude_marketplace"] = True
    return over


def _num(row: dict, key: str, default: float = 0) -> float:
    try:
        return float(row.get(key) or default)
    except (TypeError, ValueError):
        return default


def _is_marketplace(domain: str, url: str) -> bool:
    blob = f"{(domain or '').lower()} {(url or '').lower()}"
    return any(m in blob for m in MARKETPLACE_MARKERS)


def _is_shopify(domain: str, url: str) -> bool:
    blob = f"{(domain or '').lower()} {(url or '').lower()}"
    return any(m in blob for m in SHOPIFY_MARKERS)


def build_filter_config(preset_id: str = "balanced", overrides: dict | None = None) -> dict:
    cfg = dict(FILTER_PRESETS.get(normalize_filter_preset(preset_id), FILTER_PRESETS["balanced"]))
    cfg["preset_id"] = normalize_filter_preset(preset_id)
    if overrides:
        for key, val in overrides.items():
            if val is None:
                continue
            if isinstance(val, str) and not val.strip():
                continue
            cfg[key] = val
    return cfg


def _sort_rows(rows: list[dict], sort_by: str) -> list[dict]:
    sort_by = (sort_by or "score").strip().lower()
    if sort_by == "ads":
        key_fn = lambda x: (_num(x, "ads_count"), _num(x, "win_score"))
    elif sort_by in ("days", "recent", "date"):
        key_fn = lambda x: (_num(x, "max_days"), _num(x, "win_score"))
    elif sort_by == "creative":
        key_fn = lambda x: (_num(x, "creative_count"), _num(x, "win_score"))
    else:
        key_fn = lambda x: (
            x.get("label") == "winner_candidate",
            x.get("label") == "watchlist",
            _num(x, "win_score"),
            _num(x, "ads_count"),
        )
    rows = list(rows)
    rows.sort(key=key_fn, reverse=True)
    return rows


def apply_product_filters(
    rows: list[dict],
    preset_id: str = "balanced",
    overrides: dict | None = None,
) -> list[dict]:
    cfg = build_filter_config(preset_id, overrides)
    labels = set(cfg.get("labels") or ())
    conf_ok = set(cfg.get("confidence") or ())
    min_ads = int(cfg.get("min_ads") or 0)
    min_days = int(cfg.get("min_days") or 0)
    max_days = int(cfg.get("max_days") or 0)
    min_score = float(cfg.get("min_win_score") or 0)
    min_creative = int(cfg.get("min_creative") or 0)
    product_only = bool(cfg.get("product_only"))
    exclude_mp = bool(cfg.get("exclude_marketplace"))
    media_type = (cfg.get("media_type") or "any").strip().lower()
    tech = (cfg.get("tech") or "any").strip().lower()
    text_contains = (cfg.get("text_contains") or "").strip().lower()

    kept = []
    for row in rows:
        label = (row.get("label") or "").strip()
        if label == "junk":
            continue
        if labels and label not in labels:
            continue
        if conf_ok:
            if (row.get("confidence") or "").strip() not in conf_ok:
                continue
        ads = int(_num(row, "ads_count"))
        if min_ads and ads < min_ads:
            continue
        days = int(_num(row, "max_days"))
        if min_days and days < min_days:
            continue
        if max_days and days > max_days:
            continue
        if min_score and _num(row, "win_score") < min_score:
            continue
        if min_creative and int(_num(row, "creative_count")) < min_creative:
            continue
        if product_only and (row.get("landing_type") or "") != "product":
            continue
        domain = row.get("sample_domain") or row.get("domain") or ""
        url = row.get("sample_url") or ""
        if exclude_mp and _is_marketplace(domain, url):
            continue
        if tech == "shopify" and not _is_shopify(domain, url):
            continue
        if media_type == "video":
            mt = (row.get("media_type") or "").lower()
            if mt and mt != "video":
                continue
        if media_type == "image":
            mt = (row.get("media_type") or "").lower()
            if mt == "video":
                continue
        if text_contains:
            blob = f"{row.get('product')} {row.get('signature')} {domain}".lower()
            if text_contains not in blob:
                continue
        kept.append(row)

    return _sort_rows(kept, cfg.get("sort_by") or "score")
