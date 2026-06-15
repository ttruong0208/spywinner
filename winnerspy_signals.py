"""Interpret ad longevity, saturation, and traction for WinnerSpy reports."""
from __future__ import annotations


def _num(value, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def longevity_band(max_days: int, median_days: int = 0) -> str:
    d = max(0, int(max_days or 0))
    if d < 7:
        return "testing"
    if d < 14:
        return "emerging"
    if d < 30:
        return "early_validated"
    if d < 90:
        return "validated"
    if d < 180:
        return "long_running"
    return "evergreen"


LONGEVITY_LABELS = {
    "testing": ("Đang test", "Testing phase (<7d)"),
    "emerging": ("Mới nổi", "Emerging (7–13d)"),
    "early_validated": ("Qua test sớm", "Early validated (14–29d)"),
    "validated": ("Có vẻ lời", "Likely profitable (30–89d)"),
    "long_running": ("Chạy lâu", "Long-running (90–179d)"),
    "evergreen": ("Rất lâu", "Evergreen (180d+)"),
}

LONGEVITY_NOTES_VI = {
    "testing": "Ads còn quá mới — chưa đủ bằng chứng lời/lỗ.",
    "emerging": "Có thể đang trong learning phase — theo dõi thêm.",
    "early_validated": "Có thể đã qua vòng test ban đầu — chưa chắc scale.",
    "validated": "Thường là tín hiệu tích cực — vẫn cần xem landing & đối thủ.",
    "long_running": "Chạy lâu ≠ nên copy ngay — có thể brand lớn hoặc thị trường đông.",
    "evergreen": "Campaign rất lâu — thường là player mạnh; khó cho seller mới.",
}

LONGEVITY_NOTES_EN = {
    "testing": "Too early to treat as a winner signal.",
    "emerging": "May still be in learning phase.",
    "early_validated": "Survived early tests — validate before scaling.",
    "validated": "Positive proxy — still verify margin and competition.",
    "long_running": "Long runtime ≠ copy recommendation — check saturation.",
    "evergreen": "Very long campaigns often mean established players.",
}


def saturation_level(pages_count: int, ads_count: int = 0) -> str:
    """pages_count ≈ distinct advertisers on the same product cluster."""
    p = max(0, int(pages_count or 0))
    if p >= 20:
        return "extreme"
    if p >= 15:
        return "high"
    if p >= 8:
        return "moderate"
    if p >= 4:
        return "active"
    return "low"


SATURATION_LABELS = {
    "low": ("Ít shop", "Low competition"),
    "active": ("Vừa phải", "Active market"),
    "moderate": ("Khá đông", "Moderate saturation"),
    "high": ("Bão hòa cao", "High saturation"),
    "extreme": ("Rất đông", "Extreme saturation"),
}

SATURATION_NOTES_VI = {
    "low": "Ít advertiser — dễ research, chưa chắc có demand.",
    "active": "Thị trường có người chạy — sweet spot nếu có longevity tốt.",
    "moderate": "Nhiều shop — CPM có thể cao, cần differentiation.",
    "high": "Rất đông advertiser — khó vào nếu chỉ copy nguyên mẫu.",
    "extreme": "Cực kỳ đông — thường chỉ phù hợp brand/angle mạnh.",
}


def traction_type(
    longevity: str,
    saturation: str,
    creative_count: int,
    max_days: int,
) -> str:
    cc = max(0, int(creative_count or 0))
    d = max(0, int(max_days or 0))
    if d <= 90 and cc >= 3 and saturation in ("low", "active"):
        return "new_traction"
    if longevity in ("long_running", "evergreen") and saturation in ("high", "extreme"):
        return "crowded_proven"
    if longevity in ("validated", "long_running", "evergreen"):
        return "proven_demand"
    if saturation in ("high", "extreme"):
        return "crowded_uncertain"
    return "balanced"


TRACTION_LABELS = {
    "new_traction": ("Traction mới", "New traction"),
    "balanced": ("Cân bằng", "Balanced signals"),
    "proven_demand": ("Demand đã chứng minh", "Proven demand"),
    "crowded_proven": ("Đông + chạy lâu", "Crowded but proven"),
    "crowded_uncertain": ("Đông, chưa rõ", "Crowded / uncertain"),
}


def copy_risk_level(saturation: str, longevity: str, pages_count: int) -> str:
    p = max(0, int(pages_count or 0))
    if saturation in ("high", "extreme"):
        return "high"
    if saturation == "moderate" and longevity in ("long_running", "evergreen"):
        return "medium"
    if p >= 6 and longevity in ("long_running", "evergreen"):
        return "medium"
    return "low"


def saturation_score_penalty(pages_count: int) -> int:
    p = max(0, int(pages_count or 0))
    if p >= 20:
        return 4
    if p >= 15:
        return 3
    if p >= 10:
        return 2
    if p >= 6:
        return 1
    return 0


# --- Strength checklist (reference + per-product evaluation) ---

STRENGTH_GUIDE_SECTIONS = [
    {
        "title": "1. Tín hiệu Facebook Ads (cốt lõi)",
        "items": [
            ("Ngày chạy ads", "≥14d khá · ≥30d tốt · ≥90d rất mạnh — proxy ad đang lời"),
            ("Số ads cùng SP", "≥3 khá · ≥5 mạnh · ≥10 đang scale"),
            ("Creative variants", "≥3 khá · ≥5 mạnh — advertiser iterate creative"),
            ("Tỷ lệ creative/ads", "≥35% — không chỉ 1 creative spam"),
            ("Landing product page", "URL trang SP, không homepage/generic"),
            ("Shop / DTC", "Shopify hoặc store riêng — dễ reverse funnel"),
            ("Keyword match", "≥2 keyword cùng niche — demand rộng hơn"),
            ("Median days", "≥7–14d — cả nhóm ổn, không chỉ 1 ad lâu"),
        ],
    },
    {
        "title": "2. Ngưỡng WinnerSpy (label & điểm)",
        "items": [
            ("winner_candidate (high)", "win_score ≥28 · evidence ≥6 · relevance ≥2 · landing product"),
            ("winner_candidate (medium)", "win_score ≥22 · evidence ≥5 · relevance ≥1"),
            ("Strict candidate preset", "≥5 ads · ≥14 ngày · score ≥22 · DTC · bỏ marketplace"),
            ("Watchlist", "win_score ≥16 · evidence ≥4 — theo dõi, chưa đủ mạnh"),
        ],
    },
    {
        "title": "3. Loại traction",
        "items": [
            ("New traction", "≤90 ngày + ≥3 creative + ≤7 shop — vào sớm"),
            ("Proven demand", "30–179 ngày + chưa quá đông — validate thị trường"),
            ("Crowded proven", "Chạy lâu + ≥15 shop — có demand nhưng khó copy"),
        ],
    },
    {
        "title": "4. Red flags (tránh / cẩn thận)",
        "items": [
            ("Ads <7 ngày", "Còn test — chưa đủ bằng chứng"),
            ("≥15–20 shop cùng SP", "Bão hòa — CPM cao, copy_risk high"),
            ("600+ ngày + đông shop", "Brand/evergreen — khó cho seller mới"),
            ("Marketplace domain", "Amazon/Shopee/Ali — khó dropship DTC"),
            ("Penalty cao", "Service listing, junk, relevance thấp"),
        ],
    },
    {
        "title": "5. Trước khi chạy ads thật",
        "items": [
            ("Margin", "≥40–50% sau ship & phí (WinnerSpy: chưa auto — cần check AliExpress/landing)"),
            ("Supplier", "Rating & thời gian ship ổn"),
            ("Differentiation", "Góc creative/offer khác nếu market đông"),
        ],
    },
    {
        "title": "6. Velocity — tốc độ scale (mới)",
        "items": [
            ("new_ads_48h_proxy", "Số ads có days≤2 (proxy ~48h từ Ads Library)"),
            ("ads_velocity_share_3d", "≥35% ads mới trong 3 ngày = đang scale mạnh"),
            ("velocity_scaling", "≥5 ads total + share≥35% hoặc ≥4 ads ≤3 ngày"),
        ],
    },
    {
        "title": "7. Creative quality (mới)",
        "items": [
            ("video_ads_ratio", "Video ≥30% mạnh hơn chỉ image — dropship hiện đại"),
            ("unique_creative_ratio", "Nhiều fingerprint khác nhau = iterate thật"),
            ("image_spam penalty", "Nhiều ads + toàn image + creative trùng → trừ điểm"),
        ],
    },
    {
        "title": "8. Geo / platform / policy (mới)",
        "items": [
            ("scan_country", "Bão hòa tính theo quốc gia quét (US/VN/…)"),
            ("TikTok", "tt_label EXPLOSIVE/TRENDING = đa nền tảng"),
            ("policy_risk", "Blacklist brand/IP & ngách health/adult/weapon"),
            ("seasonality_risk", "SP mùa hè/đông + Trends giảm → longevity cao có thể là bẫy"),
        ],
    },
]

SHORTLIST_MIN_PASSES = 6


def compute_velocity_metrics(ads: list) -> dict:
    """Velocity from per-ad age (days since start). days≤2 ≈ last ~48h proxy."""
    ads_count = len(ads)
    day_values = [max(_num(a.get("days")), 0) for a in ads]
    ads_2d = sum(1 for d in day_values if d <= 2)
    ads_3d = sum(1 for d in day_values if d <= 3)
    ads_7d = sum(1 for d in day_values if d <= 7)
    share_2d = round(ads_2d / ads_count, 3) if ads_count else 0.0
    share_3d = round(ads_3d / ads_count, 3) if ads_count else 0.0
    share_7d = round(ads_7d / ads_count, 3) if ads_count else 0.0
    scaling = ads_count >= 5 and (share_3d >= 0.35 or ads_3d >= 4)
    return {
        "new_ads_48h_proxy": ads_2d,
        "new_ads_3d": ads_3d,
        "new_ads_7d": ads_7d,
        "ads_velocity_share_3d": share_3d,
        "ads_velocity_share_7d": share_7d,
        "velocity_scaling": scaling,
    }


def compute_creative_quality_metrics(ads: list, creative_count: int, ads_count: int) -> dict:
    video_n = sum(1 for a in ads if (a.get("media_type") or "") == "video" or _ad_is_video(a))
    image_n = sum(1 for a in ads if (a.get("media_type") or "") == "image")
    video_ratio = round(video_n / ads_count, 3) if ads_count else 0.0
    unique_ratio = round(creative_count / ads_count, 3) if ads_count else 0.0
    return {
        "video_ads_count": video_n,
        "image_ads_count": image_n,
        "video_ads_ratio": video_ratio,
        "unique_creative_ratio": unique_ratio,
        "creative_format": (
            "video_led" if video_ratio >= 0.45 else ("mixed" if video_ratio >= 0.2 else "image_led")
        ),
    }


def _ad_is_video(ad: dict) -> bool:
    u = (ad.get("media_url") or "").lower()
    return bool(u and ("video" in u or ".mp4" in u or ".webm" in u))


def velocity_signal_points(metrics: dict) -> int:
    pts = 0
    n3 = metrics.get("new_ads_3d", 0)
    share = float(metrics.get("ads_velocity_share_3d") or 0)
    pts += min(6, n3 * 2) if n3 >= 2 else 0
    if share >= 0.5:
        pts += 5
    elif share >= 0.35:
        pts += 3
    elif metrics.get("velocity_scaling"):
        pts += 2
    return min(pts, 8)


def creative_quality_signal_points(cq: dict) -> int:
    pts = 0
    vr = float(cq.get("video_ads_ratio") or 0)
    ur = float(cq.get("unique_creative_ratio") or 0)
    if vr >= 0.5:
        pts += 5
    elif vr >= 0.3:
        pts += 3
    elif vr >= 0.15:
        pts += 1
    if vr >= 0.2 and ur >= 0.35:
        pts += 2
    return min(pts, 7)


def _fnum(row: dict, key: str, default: float = 0) -> float:
    try:
        return float(row.get(key) or default)
    except (TypeError, ValueError):
        return default


def evaluate_strength_checks(row: dict) -> list[dict]:
    """Per-product checklist — each item: key, label, passed, detail, group."""
    row = ensure_product_signals(row)
    max_days = _num(row.get("max_days"))
    median_days = _num(row.get("median_days"))
    ads_count = _num(row.get("ads_count"))
    creative_count = _num(row.get("creative_count"))
    pages_count = _num(row.get("pages_count"))
    keywords_count = _num(row.get("keywords_count"))
    win_score = _fnum(row, "win_score")
    evidence = _num(row.get("evidence_points"))
    rel = _fnum(row, "relevance_score")
    creative_ratio = _fnum(row, "creative_ratio")
    landing = (row.get("landing_type") or "").strip()
    label = (row.get("label") or "").strip()
    copy_risk = (row.get("copy_risk") or "low").strip()
    is_shopify = bool(row.get("is_shopify"))
    product = (row.get("product") or "").strip().lower()
    vel_scaling = bool(row.get("velocity_scaling"))
    new_3d = _num(row.get("new_ads_3d"))
    vel_share = _fnum(row, "ads_velocity_share_3d")
    video_ratio = _fnum(row, "video_ads_ratio")
    policy = (row.get("policy_risk") or "low").strip()
    season_risk = (row.get("seasonality_risk") or "none").strip()
    tt_label = (row.get("tt_label") or "").strip().upper()
    scan_country = (row.get("scan_country") or row.get("country") or "").strip()

    checks = [
        {
            "key": "days_14",
            "label": "Ads ≥14 ngày",
            "passed": max_days >= 14,
            "detail": f"{max_days}d (≥30 tốt: {'✓' if max_days >= 30 else '—'})",
            "group": "core",
            "weight": 1,
        },
        {
            "key": "ads_3",
            "label": "≥3 ads cùng SP",
            "passed": ads_count >= 3,
            "detail": f"{ads_count} ads (≥5 mạnh: {'✓' if ads_count >= 5 else '—'})",
            "group": "core",
            "weight": 1,
        },
        {
            "key": "creative_3",
            "label": "≥3 creatives",
            "passed": creative_count >= 3,
            "detail": f"{creative_count} variants",
            "group": "core",
            "weight": 1,
        },
        {
            "key": "landing_product",
            "label": "Landing product page",
            "passed": landing == "product",
            "detail": landing or "unknown",
            "group": "core",
            "weight": 1,
        },
        {
            "key": "score_22",
            "label": "win_score ≥22",
            "passed": win_score >= 22,
            "detail": f"{int(win_score) if win_score == int(win_score) else round(win_score, 1)} (≥28: {'✓' if win_score >= 28 else '—'})",
            "group": "core",
            "weight": 1,
        },
        {
            "key": "low_saturation",
            "label": "≤10 shop (chưa bão hòa)",
            "passed": pages_count <= 10,
            "detail": f"{pages_count} shops",
            "group": "core",
            "weight": 1,
        },
        {
            "key": "label_ok",
            "label": "Label winner/watchlist",
            "passed": label in ("winner_candidate", "watchlist"),
            "detail": label or "—",
            "group": "core",
            "weight": 1,
        },
        {
            "key": "velocity_scale",
            "label": "Velocity scale (ads mới ≤3 ngày)",
            "passed": vel_scaling or new_3d >= 3 or vel_share >= 0.35,
            "detail": f"{new_3d} ads ≤3d · {int(vel_share * 100)}% share",
            "group": "core",
            "weight": 1,
        },
        {
            "key": "median_7",
            "label": "Median days ≥7",
            "passed": median_days >= 7,
            "detail": f"{median_days}d",
            "group": "bonus",
            "weight": 0,
        },
        {
            "key": "creative_ratio",
            "label": "Creative ratio ≥35%",
            "passed": creative_ratio >= 0.35,
            "detail": f"{int(creative_ratio * 100)}%",
            "group": "bonus",
            "weight": 0,
        },
        {
            "key": "evidence_5",
            "label": "Evidence ≥5/8",
            "passed": evidence >= 5,
            "detail": f"{evidence}/8",
            "group": "bonus",
            "weight": 0,
        },
        {
            "key": "relevance_pos",
            "label": "Relevance ≥1",
            "passed": rel >= 1,
            "detail": str(int(rel) if rel == int(rel) else round(rel, 1)),
            "group": "bonus",
            "weight": 0,
        },
        {
            "key": "keywords_2",
            "label": "≥2 keywords",
            "passed": keywords_count >= 2,
            "detail": str(keywords_count),
            "group": "bonus",
            "weight": 0,
        },
        {
            "key": "video_ratio",
            "label": "Video-led creatives (≥30%)",
            "passed": video_ratio >= 0.3,
            "detail": f"{int(video_ratio * 100)}% video",
            "group": "bonus",
            "weight": 0,
        },
        {
            "key": "tiktok_traction",
            "label": "TikTok traction",
            "passed": tt_label in ("EXPLOSIVE", "TRENDING", "POTENTIAL"),
            "detail": tt_label or "not checked",
            "group": "bonus",
            "weight": 0,
        },
        {
            "key": "shopify_dtc",
            "label": "Shopify / DTC store",
            "passed": is_shopify,
            "detail": "shopify" if is_shopify else "other",
            "group": "bonus",
            "weight": 0,
        },
        {
            "key": "policy_ok",
            "label": "Policy / IP risk thấp",
            "passed": policy == "low",
            "detail": policy,
            "group": "risk",
            "weight": 0,
        },
        {
            "key": "season_ok",
            "label": "Không dấu hiệu hết mùa",
            "passed": season_risk in ("none", ""),
            "detail": season_risk or "ok",
            "group": "risk",
            "weight": 0,
        },
        {
            "key": "copy_risk_ok",
            "label": "Copy risk không cao",
            "passed": copy_risk != "high",
            "detail": copy_risk,
            "group": "risk",
            "weight": 0,
        },
        {
            "key": "not_junk",
            "label": "Không junk/unknown",
            "passed": label not in ("junk", "weak") and product not in ("unknown", "none", ""),
            "detail": product[:40] if product else "—",
            "group": "risk",
            "weight": 0,
        },
    ]
    return checks


def evaluate_strength_summary(row: dict) -> dict:
    checks = evaluate_strength_checks(row)
    core = [c for c in checks if c["group"] == "core"]
    core_passed = sum(1 for c in core if c["passed"])
    core_total = len(core)
    bonus_passed = sum(1 for c in checks if c["group"] == "bonus" and c["passed"])
    risks_failed = [c for c in checks if c["group"] == "risk" and not c["passed"]]
    shortlist = core_passed >= SHORTLIST_MIN_PASSES and not risks_failed

    if (
        core_passed >= 8
        and _fnum(row, "win_score") >= 28
        and (row.get("copy_risk") or "") == "low"
        and (row.get("policy_risk") or "low") == "low"
    ):
        grade, grade_vi = "A", "Rất mạnh"
    elif shortlist and _fnum(row, "win_score") >= 22:
        grade, grade_vi = "B", "Mạnh"
    elif core_passed >= 5:
        grade, grade_vi = "C", "Khá"
    elif core_passed >= 2:
        grade, grade_vi = "D", "Yếu"
    else:
        grade, grade_vi = "F", "Rất yếu"

    if risks_failed and grade in ("A", "B"):
        grade, grade_vi = "C", "Khá (có rủi ro)"
    if (row.get("policy_risk") or "") == "high" and grade in ("A", "B"):
        grade, grade_vi = "F", "Tránh (policy)"

    return {
        "strength_checks": checks,
        "strength_core_passed": core_passed,
        "strength_core_total": core_total,
        "strength_bonus_passed": bonus_passed,
        "strength_shortlist": shortlist,
        "strength_grade": grade,
        "strength_label_vi": grade_vi,
        "strength_summary_vi": (
            f"{grade_vi} — {core_passed}/{core_total} tín hiệu cốt lõi"
            + (f" + {bonus_passed} bonus" if bonus_passed else "")
            + (" · Đủ shortlist" if shortlist else "")
        ),
    }


def enrich_product_signals(row: dict) -> dict:
    """Attach longevity / saturation / traction fields (mutates copy)."""
    out = dict(row)
    max_days = _num(out.get("max_days"))
    median_days = _num(out.get("median_days"))
    pages_count = _num(out.get("pages_count"))
    ads_count = _num(out.get("ads_count"))
    creative_count = _num(out.get("creative_count"))

    longevity = longevity_band(max_days, median_days)
    saturation = saturation_level(pages_count, ads_count)
    traction = traction_type(longevity, saturation, creative_count, max_days)
    risk = copy_risk_level(saturation, longevity, pages_count)

    lo_vi, lo_en = LONGEVITY_LABELS.get(longevity, ("", ""))
    sa_vi, sa_en = SATURATION_LABELS.get(saturation, ("", ""))
    tr_vi, tr_en = TRACTION_LABELS.get(traction, ("", ""))

    note_vi = LONGEVITY_NOTES_VI.get(longevity, "")
    sat_note = SATURATION_NOTES_VI.get(saturation, "")
    if sat_note and saturation not in ("low",):
        note_vi = f"{note_vi} {sat_note}".strip()

    note_en = LONGEVITY_NOTES_EN.get(longevity, "")
    if risk == "high":
        note_vi += " Rủi ro copy cao — validate margin trước khi test ads."
        note_en += " High copy risk — validate margin before ad spend."

    out.update(
        {
            "longevity_band": longevity,
            "longevity_label_vi": lo_vi,
            "longevity_label_en": lo_en,
            "longevity_note_vi": LONGEVITY_NOTES_VI.get(longevity, ""),
            "longevity_note_en": note_en,
            "saturation_level": saturation,
            "saturation_label_vi": sa_vi,
            "saturation_label_en": sa_en,
            "saturation_note_vi": sat_note,
            "traction_type": traction,
            "traction_label_vi": tr_vi,
            "traction_label_en": tr_en,
            "copy_risk": risk,
            "signal_summary_vi": note_vi[:280],
            "signal_summary_en": note_en[:280],
        }
    )
    out.update(evaluate_strength_summary(out))
    return out


def ensure_product_signals(row: dict) -> dict:
    out = dict(row)
    needs_full = (
        not out.get("longevity_band")
        or not out.get("saturation_level")
        or not out.get("strength_grade")
        or out.get("velocity_signal") is None and out.get("new_ads_3d") is None
    )
    if needs_full:
        return enrich_product_signals(out)
    if not out.get("strength_grade"):
        out.update(evaluate_strength_summary(out))
    return out


def render_strength_guide_html(esc) -> str:
    """Full static checklist for HTML reports."""
    parts = [
        '<section class="strength-guide">',
        '<h2>SP mạnh — bộ tín hiệu đầy đủ</h2>',
        '<p class="strength-guide-intro">'
        "Shortlist khi đạt <strong>≥6/8 tín hiệu cốt lõi</strong> "
        "và không có red flag. Đây là tín hiệu research — không phải lời khuyên mua hàng."
        "</p>",
    ]
    for section in STRENGTH_GUIDE_SECTIONS:
        parts.append(f"<h3>{esc(section['title'])}</h3><ul>")
        for title, desc in section["items"]:
            parts.append(
                f"<li><strong>{esc(title)}</strong> — {esc(desc)}</li>"
            )
        parts.append("</ul>")
    parts.append("</section>")
    return "\n".join(parts)


def render_product_strength_html(row: dict, esc) -> str:
    """Compact per-row strength checklist (core + bonus + risk)."""
    row = ensure_product_signals(row)
    grade = esc(row.get("strength_grade") or "—")
    label_vi = esc(row.get("strength_label_vi") or "")
    summary = esc(row.get("strength_summary_vi") or "")
    grade_cls = f"grade-{grade.lower()}" if grade != "—" else ""
    shortlist = row.get("strength_shortlist")
    badge = (
        '<span class="shortlist-badge">Shortlist</span>' if shortlist else ""
    )

    def _list_items(group: str) -> str:
        items = []
        for c in row.get("strength_checks") or evaluate_strength_checks(row):
            if c["group"] != group:
                continue
            mark = "✓" if c["passed"] else "✗"
            cls = "chk-ok" if c["passed"] else "chk-no"
            items.append(
                f'<li class="{cls}"><span class="chk-mark">{mark}</span>'
                f'{esc(c["label"])} <span class="chk-detail">({esc(c["detail"])})</span></li>'
            )
        return "".join(items)

    core = _list_items("core")
    bonus = _list_items("bonus")
    risk = _list_items("risk")
    bonus_block = (
        f'<p class="chk-group-title">Bonus</p><ul class="chk-list">{bonus}</ul>'
        if bonus
        else ""
    )
    risk_block = (
        f'<p class="chk-group-title">Rủi ro / red flag</p><ul class="chk-list">{risk}</ul>'
        if risk
        else ""
    )
    return (
        f'<div class="prod-strength {grade_cls}">'
        f'<div class="prod-strength-head">'
        f'<span class="grade-pill {grade_cls}">{grade}</span> '
        f'<strong>{label_vi}</strong> {badge}'
        f'<div class="prod-strength-sum">{summary}</div></div>'
        f'<p class="chk-group-title">8 tín hiệu cốt lõi</p>'
        f'<ul class="chk-list">{core}</ul>'
        f'{bonus_block}{risk_block}</div>'
    )


REPORT_DISCLAIMER_VI = (
    "Tín hiệu nghiên cứu từ Facebook Ads Library — không phải lời khuyên mua/bán. "
    "Ngày chạy lâu có thể là demand tốt hoặc thị trường đông; luôn kiểm tra margin, "
    "landing page và mức độ bão hòa trước khi test ads."
)

REPORT_DISCLAIMER_EN = (
    "Research signals from Facebook Ads Library — not buy/sell advice. "
    "Long runtime can mean proven demand or a crowded market; validate margin and "
    "saturation before spending on ads."
)
