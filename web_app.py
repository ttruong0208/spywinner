#!/usr/bin/env python3
"""
WinnerSpy Web v5 — auth, API, scheduler, admin, per-user jobs.

Run:
  chrome.exe --remote-debugging-port=9222
  pip install -r requirements-web.txt
  python web_app.py
  → http://127.0.0.1:5050
  Default admin: admin@local / admin123
"""
from __future__ import annotations

import csv
import os
import secrets
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

import web_jobs as jobs
import winnerspy_auth as auth
import winnerspy_db as db
from winnerspy_api import bp as api_bp
from winnerspy_config import (
    app_base_url,
    launch_promo_enabled,
    launch_promo_note,
    list_payment_methods,
    payment_transfer_hint,
    checkout_link_for_plan,
    plan_price_label,
    plan_price_period,
    plan_price_strike,
    saas_mode,
    upgrade_contact_note,
    upgrade_contact_url,
)
from winnerspy_plans import (
    CHOOSABLE_PLANS,
    effective_plan,
    normalize_choose_plan,
    plan_feature_labels,
    plan_rank,
)
from winnerspy_filters import list_presets_for_ui, preset_meta
from winnerspy_gallery import build_gallery_cards
from winnerspy_mail import send_welcome_email, smtp_configured


def _send_user_verification_code(to_email: str, code: str) -> bool:
    """Send 6-digit code — works even if winnerspy_mail on server is outdated."""
    try:
        from winnerspy_mail import send_verification_code_email

        return send_verification_code_email(to_email, code)
    except ImportError:
        pass

    if not smtp_configured():
        return False

    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    host = os.environ.get("WINNERSPY_SMTP_HOST", "").strip()
    port = int(os.environ.get("WINNERSPY_SMTP_PORT", "587"))
    user = os.environ.get("WINNERSPY_SMTP_USER", "").strip()
    password = os.environ.get("WINNERSPY_SMTP_PASSWORD", "").strip()
    from_addr = os.environ.get("WINNERSPY_SMTP_FROM", "").strip()
    use_tls = os.environ.get("WINNERSPY_SMTP_TLS", "1").strip().lower() in ("1", "true", "yes")
    verify_url = f"{app_base_url()}/verify-pending"

    subject = f"Your WinnerSpy verification code: {code}"
    text = (
        f"Hi,\n\nYour WinnerSpy verification code is:\n\n  {code}\n\n"
        f"Enter it here: {verify_url}\n\nCode expires in 15 minutes.\n\n— WinnerSpy\n"
    )
    html = (
        f"<p>Hi,</p><p>Your WinnerSpy verification code is:</p>"
        f'<p style="font-size:28px;font-weight:800;letter-spacing:0.25em">{code}</p>'
        f'<p>Enter it on the <a href="{verify_url}">verification page</a>.</p>'
        f"<p><small>Expires in 15 minutes.</small></p>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        if user and password:
            server.login(user, password)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as exc:
        print(f"[WinnerSpy] Verification mail error: {exc}")
        return False
from winnerspy_trust import beta_guarantee_text, positioning_line, support_hours, support_zalo_url
from winnerspy_scheduler import start_scheduler
from winnerspy_security import (
    admin_ip_allowed,
    admin_url_prefix,
    apply_session_cookie_flags,
    ensure_csrf_token,
    production_mode,
    security_headers,
    validate_csrf,
    validate_production_config,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("WINNERSPY_SECRET", secrets.token_hex(16))
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024
apply_session_cookie_flags(app)

ADMIN_PREFIX = admin_url_prefix()

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

app.register_blueprint(api_bp)

try:
    db.init_db()
    jobs.ensure_dirs()
except Exception as exc:
    print(f"[WinnerSpy] init_db error: {exc}")

_UNVERIFIED_ENDPOINTS = frozenset({
    "verify_pending",
    "verify_email",
    "resend_verification",
    "logout",
    "login",
    "register",
    "choose_plan",
    "home",
    "static",
})

ROADMAP = [
    {"v": "v1", "title": "Web form + job + log + report", "done": True},
    {"v": "v2", "title": "Login / multi-user", "done": True},
    {"v": "v2", "title": "Scheduled scans (cron)", "done": True},
    {"v": "v3", "title": "REST API key", "done": True},
    {"v": "v4", "title": "Free / Pro / VIP + quotas", "done": True},
    {"v": "v5", "title": "Admin + webhook + settings", "done": True},
]


class User(UserMixin):
    def __init__(self, row: dict):
        self.id = row["id"]
        self.email = row["email"]
        self.plan = row["plan"]
        self.role = row.get("role", "user")
        self.api_key = row.get("api_key", "")
        self.webhook_url = row.get("webhook_url", "")
        self.cdp_url = row.get("cdp_url") or "http://127.0.0.1:9222"
        self.email_verified = auth.is_user_email_verified(row)
        self._row = row

    @property
    def is_admin(self) -> bool:
        """Chỉ role=admin — không tin field plan (tránh leo quyền)."""
        return self.role == "admin"


@login_manager.user_loader
def load_user(user_id: str):
    row = db.get_user_by_id(int(user_id))
    return User(row) if row else None


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(404)
        if not admin_ip_allowed():
            abort(404)
        return fn(*args, **kwargs)

    return wrapper


def admin_post_required(fn):
    """Admin POST — CSRF do csrf_protect_post xử lý."""
    return admin_required(fn)


@app.before_request
def prepare_csrf_token():
    ensure_csrf_token()
    return None


@app.before_request
def require_verified_email():
    if not auth.email_verification_enabled():
        return None
    if not current_user.is_authenticated:
        return None
    if current_user.is_admin:
        return None
    ep = request.endpoint or ""
    if ep in _UNVERIFIED_ENDPOINTS or ep.startswith("static"):
        return None
    row = db.get_user_by_id(current_user.id)
    if auth.is_user_email_verified(row):
        return None
    return redirect(url_for("verify_pending"))


@app.before_request
def csrf_protect_post():
    if request.method != "POST":
        return None
    ep = request.endpoint or ""
    if ep.startswith("api_v1."):
        return None
    if request.is_json:
        return None
    if validate_csrf():
        return None
    flash("Session expired or invalid form — refresh (F5) and try again.", "error")
    return redirect(request.referrer or url_for("home"))


@app.after_request
def add_security_headers(response):
    for key, val in security_headers().items():
        response.headers[key] = val
    return response


if not production_mode():
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(Exception)
    def _log_unhandled_error(exc):
        if isinstance(exc, HTTPException):
            return exc
        import traceback

        traceback.print_exc()
        return (
            "<h1>Dev error</h1><pre>"
            + traceback.format_exc().replace("<", "&lt;")
            + "</pre><p><a href='/'>Home</a></p>",
            500,
        )


@app.context_processor
def inject_globals():
    base = {
        "app_version": "v5",
        "asset_v": "20260531pay",
        "saas_mode": saas_mode(),
        "registration_mode": auth.registration_mode(),
        "registration_allowed": auth.registration_allowed(),
        "email_verification_enabled": auth.email_verification_enabled(),
        "upgrade_url": upgrade_contact_url(),
        "upgrade_note": upgrade_contact_note(),
        "plan_labels": {
            "free": plan_feature_labels("free"),
            "pro": plan_feature_labels("pro"),
            "vip": plan_feature_labels("vip"),
        },
        "plan_prices": {p: plan_price_label(p) for p in CHOOSABLE_PLANS},
        "plan_prices_strike": {p: plan_price_strike(p) for p in ("pro", "vip")},
        "plan_price_period": plan_price_period(),
        "launch_promo": launch_promo_enabled(),
        "launch_promo_note": launch_promo_note(),
        "filter_presets": list_presets_for_ui(),
        "preset_labels": jobs.PRESET_LABELS,
        "csrf_token": ensure_csrf_token(),
        "admin_path": admin_url_prefix(),
        "production_mode": production_mode(),
        "support_zalo_url": support_zalo_url(),
        "support_hours": support_hours(),
        "beta_guarantee": beta_guarantee_text(),
        "positioning_line": positioning_line(),
        "app_url": app_base_url(),
        "api_base_url": f"{app_base_url()}/api/v1",
    }
    if current_user.is_authenticated:
        limits = db.plan_limits(current_user.plan if current_user.plan != "admin" else "vip")
        recent_jobs = db.list_jobs_for_user(current_user.id, 5)
        base.update({
            "user_limits": limits,
            "scans_today": db.count_scans_today(current_user.id),
            "show_onboarding": not session.get("onboarding_dismissed") and len(recent_jobs) == 0,
            "user_job_count": len(recent_jobs),
        })
    return base


def _safe_next_url(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("/") and not raw.startswith("//"):
        return raw
    return None


def _redirect_after_auth(target_plan: str):
    target_plan = normalize_choose_plan(target_plan)
    row = db.get_user_by_id(current_user.id) if current_user.is_authenticated else None
    if auth.email_verification_enabled() and row and not auth.is_user_email_verified(row):
        session["pending_plan"] = target_plan
        return redirect(url_for("verify_pending"))
    nxt = _safe_next_url(request.args.get("next") or request.form.get("next"))
    if nxt:
        return redirect(nxt)
    if not current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    cur = effective_plan(current_user.plan)
    if target_plan == "free":
        return redirect(url_for("welcome"))
    if plan_rank(cur) >= plan_rank(target_plan):
        return redirect(url_for("dashboard"))
    return redirect(url_for("checkout", plan=target_plan))


def _redirect_logged_in_for_plan(plan: str):
    plan = normalize_choose_plan(plan)
    cur = effective_plan(current_user.plan)
    if plan == "free":
        return redirect(url_for("welcome"))
    if plan_rank(cur) >= plan_rank(plan):
        flash("You already have this plan or higher.", "ok")
        return redirect(url_for("dashboard"))
    return redirect(url_for("checkout", plan=plan))


def _send_verification_email_for_user(row: dict) -> str:
    code = str(row.get("verify_token") or "").strip()
    if not code or not db.verify_token_valid(row) or len(code) != 6:
        code = db.rotate_verify_token(row["id"])
        row = db.get_user_by_id(row["id"]) or row
        code = str(row.get("verify_token") or code)
    if _send_user_verification_code(row["email"], code):
        session.pop("dev_verify_code", None)
    else:
        session["dev_verify_code"] = code
    return code


@app.route("/choose-plan/<plan>")
@app.route("/chon-goi/<plan>")  # legacy URL
def choose_plan(plan):
    """Landing Free/Pro/VIP → register/login → checkout for chosen plan."""
    plan = normalize_choose_plan(plan)
    if current_user.is_authenticated:
        return _redirect_logged_in_for_plan(plan)
    if auth.registration_allowed():
        return redirect(url_for("register", plan=plan))
    flash("Registration is closed — log in if you have an account, then complete checkout.", "error")
    return redirect(url_for("login", plan=plan))


@app.route("/")
def home():
    if current_user.is_authenticated:
        row = db.get_user_by_id(current_user.id)
        if auth.email_verification_enabled() and not auth.is_user_email_verified(row):
            return redirect(url_for("verify_pending"))
        return redirect(url_for("dashboard"))
    return render_template("home.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        row = db.get_user_by_id(current_user.id)
        if auth.email_verification_enabled() and not auth.is_user_email_verified(row):
            return redirect(url_for("verify_pending"))
        return _redirect_logged_in_for_plan(request.args.get("plan", "free"))
    target_plan = normalize_choose_plan(request.args.get("plan"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        target_plan = normalize_choose_plan(request.form.get("plan") or request.args.get("plan"))
        ok, msg = auth.check_rate_limit(f"login:{auth.client_ip()}:{email}")
        if not ok:
            flash(msg, "error")
        else:
            row = db.get_user_by_email(email)
            if row and check_password_hash(row["password_hash"], password):
                login_user(User(row))
                session["pending_plan"] = target_plan
                if auth.email_verification_enabled() and not auth.is_user_email_verified(row):
                    flash("Verify your email before running scans.", "error")
                    return redirect(url_for("verify_pending"))
                return _redirect_after_auth(target_plan)
            flash("Invalid email or password.", "error")
    return render_template(
        "login.html",
        target_plan=target_plan,
        next_url=_safe_next_url(request.args.get("next")),
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        row = db.get_user_by_id(current_user.id)
        if auth.email_verification_enabled() and not auth.is_user_email_verified(row):
            return redirect(url_for("verify_pending"))
        return _redirect_logged_in_for_plan(request.args.get("plan", "free"))
    target_plan = normalize_choose_plan(request.args.get("plan"))
    mode = auth.registration_mode()
    if mode == "closed":
        flash("Registration is closed. Contact admin or log in if you already have an account.", "error")
        return redirect(url_for("login", plan=target_plan))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        invite = request.form.get("invite_code", "").strip()
        target_plan = normalize_choose_plan(request.form.get("plan") or request.args.get("plan"))
        ok, msg = auth.check_rate_limit(f"register:{auth.client_ip()}")
        if not ok:
            flash(msg, "error")
        elif mode == "invite" and not auth.verify_invite_code(invite):
            flash("Invalid invite code.", "error")
        else:
            match_ok, match_msg = auth.passwords_match(password, password_confirm)
            if not match_ok:
                flash(match_msg, "error")
            else:
                pw_ok, pw_msg = auth.validate_password(password)
                if not pw_ok:
                    flash(pw_msg, "error")
                elif db.get_user_by_email(email):
                    flash("Email already registered.", "error")
                else:
                    uid = db.create_user(email, generate_password_hash(password))
                    row = db.get_user_by_id(uid)
                    login_user(User(row))
                    session["pending_plan"] = target_plan
                    _send_verification_email_for_user(row)
                    if smtp_configured():
                        flash(
                            "Account created. We sent a 6-digit code to your email — enter it to continue.",
                            "ok",
                        )
                    else:
                        flash(
                            "Account created. Enter the verification code shown below (SMTP not configured yet).",
                            "warn",
                        )
                    return redirect(url_for("verify_pending"))
    return render_template(
        "register.html",
        registration_mode=mode,
        target_plan=target_plan,
    )


@app.route("/verify-pending", methods=["GET", "POST"])
@login_required
def verify_pending():
    row = db.get_user_by_id(current_user.id)
    if auth.is_user_email_verified(row):
        return _redirect_after_auth(session.get("pending_plan", "free"))

    if request.method == "POST":
        code = (request.form.get("verify_code") or "").strip()
        row = db.get_user_by_id(current_user.id)
        ok, msg = auth.check_rate_limit(f"verify_code:{current_user.id}")
        if not ok:
            flash(msg, "error")
        elif not code:
            flash("Enter the 6-digit code from your email.", "error")
        elif not db.verify_token_valid(row):
            flash("Code expired — click Resend code for a new one.", "error")
        elif not auth.secrets_compare(code, str(row.get("verify_token") or "")):
            flash("Incorrect code — check your email and try again.", "error")
        else:
            db.mark_email_verified(current_user.id)
            session.pop("dev_verify_code", None)
            fresh = db.get_user_by_id(current_user.id)
            flash("Email verified. Welcome to WinnerSpy!", "ok")
            dash_abs = f"{app_base_url()}/dashboard"
            if send_welcome_email(fresh["email"], dash_abs):
                flash("Sent a getting-started email — check your inbox.", "ok")
            return _redirect_after_auth(session.get("pending_plan", "free"))

    dev_code = session.get("dev_verify_code")
    return render_template(
        "verify_pending.html",
        email=current_user.email,
        smtp_ok=smtp_configured(),
        dev_verify_code=dev_code,
    )


@app.route("/verify-email")
def verify_email():
    code = (request.args.get("code") or request.args.get("token") or "").strip()
    row = db.get_user_by_verify_token(code)
    if not row:
        flash("Invalid or expired code.", "error")
        return redirect(url_for("login"))
    if not db.verify_token_valid(row):
        flash("Code expired. Log in and request a new code.", "error")
        return redirect(url_for("login"))
    db.mark_email_verified(row["id"])
    fresh = db.get_user_by_id(row["id"])
    login_user(User(fresh))
    flash("Email verified. Welcome to WinnerSpy!", "ok")
    dash_abs = f"{app_base_url()}/dashboard"
    if send_welcome_email(fresh["email"], dash_abs):
        flash("Sent a getting-started email — check your inbox.", "ok")
    return _redirect_after_auth(session.get("pending_plan", "free"))


@app.route("/resend-verification", methods=["POST"])
@login_required
def resend_verification():
    row = db.get_user_by_id(current_user.id)
    if auth.is_user_email_verified(row):
        return redirect(url_for("dashboard"))
    ok, msg = auth.check_rate_limit(f"verify_resend:{current_user.id}")
    if not ok:
        flash(msg, "error")
    else:
        db.rotate_verify_token(current_user.id)
        row = db.get_user_by_id(current_user.id)
        _send_verification_email_for_user(row)
        if smtp_configured():
            flash("New verification code sent to your email.", "ok")
        else:
            flash("SMTP not configured — use the code shown on this page.", "warn")
    return redirect(url_for("verify_pending"))


@app.route("/onboarding/dismiss", methods=["POST"])
@login_required
def dismiss_onboarding():
    session["onboarding_dismissed"] = True
    return redirect(url_for("dashboard"))


@app.route("/welcome")
@login_required
def welcome():
    """Sau đăng ký Free — upsell Pro/VIP trước khi vào dashboard."""
    cur = effective_plan(current_user.plan)
    if plan_rank(cur) > plan_rank("free"):
        return redirect(url_for("dashboard"))
    return render_template(
        "welcome.html",
        limits=db.plan_limits("free"),
    )


@app.route("/checkout/<plan>", methods=["GET", "POST"])
@login_required
def checkout(plan):
    plan = normalize_choose_plan(plan)
    if plan == "free":
        return redirect(url_for("welcome"))
    cur = effective_plan(current_user.plan)
    if plan_rank(cur) >= plan_rank(plan):
        flash("You already have this plan or higher.", "ok")
        return redirect(url_for("dashboard"))

    pending = db.get_latest_upgrade_request(current_user.id, plan, status="pending")

    if request.method == "POST":
        note = request.form.get("transfer_note", "").strip()
        if not pending:
            db.create_upgrade_request(current_user.id, plan, note)
            flash(
                f"Payment submitted for {plan.upper()} — pending verification. "
                "Your account stays on Free until we confirm (usually within 24 hours).",
                "warn",
            )
        else:
            flash(
                "Your payment is still pending review — we will activate your plan after verification.",
                "warn",
            )
        return redirect(url_for("checkout", plan=plan))

    labels = plan_feature_labels(plan)
    limits = db.plan_limits(plan)
    price = plan_price_label(plan)
    memo = payment_transfer_hint(current_user.email, plan)
    return render_template(
        "checkout.html",
        plan=plan,
        limits=limits,
        labels=labels,
        price=price,
        price_period=plan_price_period(),
        transfer_memo=memo,
        payment_methods=list_payment_methods(plan, price, memo, current_user.email),
        checkout_url=checkout_link_for_plan(plan),
        pending=pending,
    )


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


@app.route("/pricing")
@app.route("/goi")  # legacy URL
@login_required
def pricing_page():
    plan = current_user.plan if current_user.plan != "admin" else "vip"
    return render_template(
        "pricing.html",
        limits=db.plan_limits(plan),
        all_plans={name: db.plan_limits(name) for name in ("free", "pro", "vip")},
        current_plan=current_user.plan,
    )


@app.route("/app")
@login_required
def dashboard():
    limits = db.plan_limits(current_user.plan if current_user.plan != "admin" else "vip")
    return render_template(
        "index.html",
        presets=jobs.PRESETS,
        jobs=db.list_jobs_for_user(current_user.id, 25),
        roadmap=ROADMAP,
        cdp_default=current_user.cdp_url,
        limits=limits,
        scans_today=db.count_scans_today(current_user.id),
        default_filter_preset="balanced",
    )


@app.route("/api/cdp-check", methods=["POST"])
@login_required
def api_cdp_check():
    data = request.get_json(silent=True) or {}
    cdp = data.get("cdp") or request.form.get("cdp") or current_user.cdp_url
    return jsonify(jobs.check_cdp(cdp))


@app.route("/scan", methods=["POST"])
@login_required
def scan():
    opts = {
        "country": request.form.get("country", "US").strip().upper(),
        "preset": request.form.get("preset", "cleaning_us").strip(),
        "keywords": request.form.get("keywords", "").strip(),
        "scroll": int(request.form.get("scroll") or 8),
        "top": int(request.form.get("top") or 20),
        "tiktok": request.form.get("tiktok") == "on",
        "tiktok_limit": int(request.form.get("tiktok_limit") or 8),
        "google_trends": request.form.get("google_trends") == "on",
        "gt_limit": int(request.form.get("gt_limit") or 10),
        "cdp": request.form.get("cdp", current_user.cdp_url).strip(),
        "from_raw": request.form.get("from_raw") == "on",
        "filter_preset": request.form.get("filter_preset", "balanced").strip(),
        "filter_media": request.form.get("filter_media", "any").strip(),
        "filter_tech": request.form.get("filter_tech", "any").strip(),
        "filter_min_ads": request.form.get("filter_min_ads", "").strip(),
        "filter_min_days": request.form.get("filter_min_days", "").strip(),
        "filter_max_days": request.form.get("filter_max_days", "").strip(),
        "filter_sort": request.form.get("filter_sort", "score").strip(),
        "filter_product_only": request.form.get("filter_product_only") == "on",
        "filter_no_marketplace": request.form.get("filter_no_marketplace") == "on",
    }
    try:
        job_id = jobs.start_job(current_user.id, opts, source="web")
    except (PermissionError, ValueError) as e:
        flash(str(e), "error")
        return redirect(url_for("dashboard"))
    return redirect(url_for("job_detail", job_id=job_id))


@app.route("/job/<job_id>")
@login_required
def job_detail(job_id):
    job = db.get_job(job_id)
    if not job or job["user_id"] != current_user.id:
        if not current_user.is_admin:
            abort(404)
    uid = job["user_id"] if job else current_user.id
    meta = jobs.load_job_meta(uid, job_id) or job
    if not meta:
        abort(404)
    rows = load_winner_preview(uid, job_id, limit=50)
    fp = (meta.get("opts") or {}).get("filter_preset", "balanced")
    job_dir = jobs.job_path(uid, job_id)
    raw_csv = job_dir / "raw_ads.csv"
    has_raw_ads = raw_csv.is_file() and raw_csv.stat().st_size > 200
    raw_ad_count = 0
    if has_raw_ads:
        try:
            with raw_csv.open(encoding="utf-8-sig", newline="") as f:
                raw_ad_count = max(0, sum(1 for _ in csv.reader(f)) - 1)
        except OSError:
            raw_ad_count = 0
    return render_template(
        "job.html",
        job=meta,
        log=jobs.tail_log(uid, job_id, 120),
        rows=rows,
        filter_preset=fp,
        filter_preset_meta=preset_meta(fp),
        filter_presets=list_presets_for_ui(),
        has_raw_ads=has_raw_ads,
        raw_ad_count=raw_ad_count,
    )


def _job_access(job_id: str) -> tuple[dict, int, Path]:
    job = db.get_job(job_id)
    if not job:
        abort(404)
    if job["user_id"] != current_user.id and not current_user.is_admin:
        abort(403)
    uid = job["user_id"]
    return job, uid, jobs.job_path(uid, job_id)


@app.route("/job/<job_id>/gallery")
@login_required
def job_gallery(job_id):
    job, uid, job_dir = _job_access(job_id)
    meta = jobs.load_job_meta(uid, job_id) or job
    opts = meta.get("opts") or {}
    country = (opts.get("country") or "US").strip().upper()
    cards = build_gallery_cards(job_dir, limit=180, country=country)
    country_names = {"US": "United States", "VN": "Vietnam", "ALL": "All regions"}
    return render_template(
        "job_gallery.html",
        job=meta,
        ads=cards,
        country=country,
        country_label=country_names.get(country, country),
        filter_presets=list_presets_for_ui(),
    )


@app.route("/api/job/<job_id>/ads")
@login_required
def api_job_ads(job_id):
    job, uid, job_dir = _job_access(job_id)
    opts = (jobs.load_job_meta(uid, job_id) or job).get("opts") or {}
    country = (opts.get("country") or "US").strip().upper()
    cards = build_gallery_cards(
        job_dir,
        limit=int(request.args.get("limit", 120)),
        country=country,
        only_winners=request.args.get("winners") == "1",
        media=request.args.get("media", "any"),
        min_days=int(request.args.get("min_days", 0) or 0),
        q=request.args.get("q", ""),
    )
    return jsonify({"ads": cards, "count": len(cards)})


@app.route("/api/job/<job_id>/status")
@login_required
def api_job_status(job_id):
    job = db.get_job(job_id)
    if not job or (job["user_id"] != current_user.id and not current_user.is_admin):
        abort(404)
    uid = job["user_id"]
    meta = jobs.load_job_meta(uid, job_id) or job
    return jsonify({
        **meta,
        "log_tail": jobs.tail_log(uid, job_id, 60),
    })


@app.route("/job/<job_id>/files/<path:filename>")
@login_required
def job_file(job_id, filename):
    job = db.get_job(job_id)
    if not job or (job["user_id"] != current_user.id and not current_user.is_admin):
        abort(404)
    directory = jobs.job_path(job["user_id"], job_id)
    if not directory.is_dir():
        abort(404)
    safe = Path(filename).name
    return send_from_directory(directory, safe, as_attachment=(request.args.get("dl") == "1"))


def _r_module():
    import importlib.util

    path = jobs.BASE_DIR / "r.py"
    spec = importlib.util.spec_from_file_location("winnerspy_r", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@app.route("/job/<job_id>/report")
@login_required
def job_report(job_id):
    job = db.get_job(job_id)
    if not job or (job["user_id"] != current_user.id and not current_user.is_admin):
        abort(404)
    directory = jobs.job_path(job["user_id"], job_id)
    report = directory / "report.html"
    if not report.is_file():
        final = directory / "final_research_results.csv"
        winners = directory / "winner_products.csv"
        source = final if final.is_file() else winners
        if source.is_file():
            _r_module().export_html_report(str(source), str(report))
    if not report.is_file():
        abort(404)
    return send_from_directory(directory, "report.html")


def load_winner_preview(user_id: int, job_id: str, limit: int = 50) -> list[dict]:
    d = jobs.job_path(user_id, job_id)
    for name in ("final_research_results.csv", "scored_products.csv", "winner_products.csv"):
        p = d / name
        if not p.is_file():
            continue
        with p.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        rows.sort(
            key=lambda r: float(r.get("final_priority") or r.get("win_score") or 0),
            reverse=True,
        )
        out = []
        for r in rows[:limit]:
            out.append({
                "product": r.get("product") or r.get("signature") or "?",
                "score": r.get("final_priority") or r.get("win_score") or "",
                "label": r.get("label") or "",
                "confidence": r.get("confidence") or "",
                "matches_preset": str(r.get("matches_preset") or ""),
                "tt_label": r.get("tt_label") or "",
                "domain": r.get("sample_domain") or r.get("domain") or "",
                "ads_count": r.get("ads_count") or "",
                "max_days": r.get("max_days") or "",
                "creative_count": r.get("creative_count") or "",
                "landing_type": r.get("landing_type") or "",
                "url": r.get("sample_url") or "",
            })
        return out
    return []


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user = db.get_user_by_id(current_user.id)
    limits = db.plan_limits(current_user.plan if current_user.plan != "admin" else "vip")
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "regen_key":
            if not limits["api"]:
                flash("Free plan has no API. Upgrade to Pro.", "error")
            else:
                key = db.regenerate_api_key(current_user.id)
                flash(f"New API key: {key}", "ok")
        else:
            db.update_user_settings(
                current_user.id,
                webhook_url=request.form.get("webhook_url", "").strip(),
                cdp_url=request.form.get("cdp_url", "http://127.0.0.1:9222").strip(),
            )
            flash("Settings saved.", "ok")
        return redirect(url_for("settings"))
    user = db.get_user_by_id(current_user.id)
    return render_template("settings.html", user=user, limits=limits)


@app.route("/schedules", methods=["GET", "POST"])
@login_required
def schedules_page():
    limits = db.plan_limits(current_user.plan if current_user.plan != "admin" else "vip")
    if not limits["schedules"]:
        flash("Your plan does not include scheduled scans.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        action = request.form.get("action")
        if action == "delete":
            db.delete_schedule(int(request.form["schedule_id"]), current_user.id)
            flash("Schedule deleted.", "ok")
        elif action == "toggle":
            db.toggle_schedule(
                int(request.form["schedule_id"]),
                current_user.id,
                request.form.get("enabled") == "1",
            )
        else:
            existing = db.list_schedules(current_user.id)
            if len(existing) >= limits["schedules"]:
                flash(f"Maximum {limits['schedules']} schedules.", "error")
            else:
                opts = {
                    "country": request.form.get("country", "US"),
                    "preset": request.form.get("preset", "cleaning_us"),
                    "keywords": request.form.get("keywords", ""),
                    "scroll": int(request.form.get("scroll") or 8),
                    "tiktok": request.form.get("tiktok") == "on",
                    "tiktok_limit": int(request.form.get("tiktok_limit") or 15),
                }
                days = ",".join(request.form.getlist("days") or ["0", "1", "2", "3", "4", "5", "6"])
                db.create_schedule(
                    current_user.id,
                    request.form.get("name", "Auto scan"),
                    int(request.form.get("hour", 8)),
                    int(request.form.get("minute", 0)),
                    days,
                    opts,
                )
                flash("Schedule created.", "ok")
        return redirect(url_for("schedules_page"))

    return render_template(
        "schedules.html",
        schedules=db.list_schedules(current_user.id),
        presets=jobs.PRESETS,
        limits=limits,
    )


@app.route(f"/{ADMIN_PREFIX}")
@admin_required
def admin_dashboard():
    return render_template(
        "admin.html",
        users=db.list_users(),
        jobs=db.list_all_jobs(40),
        upgrade_requests=db.list_pending_upgrade_requests(30),
    )


@app.route(f"/{ADMIN_PREFIX}/user/<int:user_id>/plan", methods=["POST"])
@admin_post_required
def admin_set_plan(user_id):
    plan = request.form.get("plan", "free")
    if plan in ("free", "pro", "vip"):
        db.set_user_plan(user_id, plan)
        req_id = request.form.get("upgrade_request_id", type=int)
        if req_id:
            db.mark_upgrade_request_done(req_id)
        flash("Plan updated.", "ok")
    return redirect(url_for("admin_dashboard"))


@app.route(f"/{ADMIN_PREFIX}/user/<int:user_id>/verify-email", methods=["POST"])
@admin_post_required
def admin_verify_user_email(user_id):
    db.mark_email_verified(user_id)
    flash("User email marked verified.", "ok")
    return redirect(url_for("admin_dashboard"))


@app.route("/docs/api")
@login_required
def api_docs():
    return render_template("api_docs.html", user=db.get_user_by_id(current_user.id))


if __name__ == "__main__":
    cfg_errors = validate_production_config()
    for msg in cfg_errors:
        print(f"[WinnerSpy SECURITY] {msg}")
    if production_mode() and cfg_errors:
        raise SystemExit("Stopped: unsafe production config (see log above).")
    db.init_db()
    jobs.ensure_dirs()
    start_scheduler()
    print("WinnerSpy Web v5: http://127.0.0.1:5050")
    if production_mode():
        print(f"Production ON — admin path: /{ADMIN_PREFIX}")
    else:
        print(f"Dev — admin: /{ADMIN_PREFIX} (set WINNERSPY_PRODUCTION=1 on server)")
    if saas_mode():
        print("SaaS mode ON — users do not need local Chrome")
    else:
        print("Dev mode — run start_chrome_debug.bat before scanning")
    print("Registration: WINNERSPY_ALLOW_REGISTER=1 or WINNERSPY_INVITE_CODE=...")
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
