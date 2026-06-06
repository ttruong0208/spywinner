"""Runtime flags — local dev vs SaaS production."""
from __future__ import annotations

import os


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def saas_mode() -> bool:
    """True = users only use the web; Chrome/CDP runs on the server (WINNERSPY_SAAS_MODE=1)."""
    return _truthy("WINNERSPY_SAAS_MODE", "0")


def server_cdp_url() -> str:
    return os.environ.get("WINNERSPY_CDP_URL", "http://127.0.0.1:9222").strip()


def upgrade_contact_url() -> str:
    """Support / payment link — e.g. Calendly, PayPal, Telegram."""
    return os.environ.get("WINNERSPY_UPGRADE_URL", "").strip()


def upgrade_contact_note() -> str:
    return os.environ.get(
        "WINNERSPY_UPGRADE_NOTE",
        "Email us your WinnerSpy account + plan (Pro/VIP). We activate within 24 hours after payment.",
    ).strip()


def plan_price_label(plan: str) -> str:
    prices = {
        "free": "$0",
        "pro": os.environ.get("WINNERSPY_PRICE_PRO", "$29").strip(),
        "vip": os.environ.get("WINNERSPY_PRICE_VIP", "$79").strip(),
    }
    return prices.get(plan, "Contact")


def plan_price_strike(plan: str) -> str:
    strikes = {
        "pro": os.environ.get("WINNERSPY_PRICE_PRO_STRIKE", "$49").strip(),
        "vip": os.environ.get("WINNERSPY_PRICE_VIP_STRIKE", "$149").strip(),
    }
    return strikes.get(plan, "")


def launch_promo_enabled() -> bool:
    return _truthy("WINNERSPY_LAUNCH_PROMO", "1")


def launch_promo_note() -> str:
    return os.environ.get(
        "WINNERSPY_LAUNCH_PROMO_NOTE",
        "Launch beta pricing for early users — will increase as we add capacity.",
    ).strip()


def plan_price_period() -> str:
    return os.environ.get("WINNERSPY_PRICE_PERIOD", "/mo").strip()


def payment_bank_info() -> str:
    """Short fallback line when no payment env vars are set."""
    return os.environ.get(
        "WINNERSPY_PAYMENT_BANK",
        "We accept PayPal, Wise (USD), and USDT (TRC20). Include your payment reference in the transfer note.",
    ).strip()


def payment_transfer_hint(email: str, plan: str) -> str:
    slug = plan.upper()
    short = email.split("@")[0][:12]
    return os.environ.get(
        "WINNERSPY_PAYMENT_MEMO",
        f"WS-{slug}-{short}",
    ).replace("{email}", email).replace("{plan}", plan.upper())


def checkout_link_for_plan(plan: str) -> str:
    """Direct payment page (Stripe, Gumroad, Lemon Squeezy, PayPal subscription…)."""
    plan = (plan or "").strip().lower()
    by_plan = {
        "pro": os.environ.get("WINNERSPY_CHECKOUT_URL_PRO", "").strip(),
        "vip": os.environ.get("WINNERSPY_CHECKOUT_URL_VIP", "").strip(),
    }
    return by_plan.get(plan) or os.environ.get("WINNERSPY_CHECKOUT_URL", "").strip()


def list_payment_methods(
    plan: str,
    price: str,
    memo: str,
    email: str,
) -> list[dict]:
    """Checkout UI — ordered payment options (USD / international)."""
    period = plan_price_period()
    amount_usd = price.replace("$", "").strip() or "0"
    methods: list[dict] = []

    checkout_url = checkout_link_for_plan(plan)
    if checkout_url:
        methods.append(
            {
                "id": "checkout",
                "title": "Pay online (card / PayPal)",
                "detail": f"Pay <strong>{price}{period}</strong> on our checkout page, then submit confirmation below.",
                "action_label": f"Pay {price}{period}",
                "action_url": checkout_url,
                "primary": True,
            }
        )

    paypal_me = os.environ.get("WINNERSPY_PAYPAL_ME", "").strip()
    paypal_email = os.environ.get("WINNERSPY_PAYPAL_EMAIL", "").strip()
    if paypal_me or paypal_email:
        if paypal_me.startswith("http"):
            paypal_url = paypal_me
        elif paypal_me:
            paypal_url = f"https://www.paypal.me/{paypal_me.strip('/')}/{amount_usd}USD"
        else:
            paypal_url = os.environ.get("WINNERSPY_PAYPAL_URL", "").strip()
        recipient = paypal_me if paypal_me and not paypal_me.startswith("http") else paypal_email
        methods.append(
            {
                "id": "paypal",
                "title": "PayPal",
                "detail": (
                    f"Send <strong>{price}{period}</strong> via PayPal"
                    + (f" to <code>{recipient}</code>" if recipient else "")
                    + f". Add note/memo: <code>{memo}</code>."
                ),
                "action_label": "Open PayPal",
                "action_url": paypal_url or None,
                "copy": recipient or paypal_email,
            }
        )

    wise = (
        os.environ.get("WINNERSPY_WISE_EMAIL", "").strip()
        or os.environ.get("WINNERSPY_WISE_TAG", "").strip()
    )
    if wise:
        methods.append(
            {
                "id": "wise",
                "title": "Wise (USD transfer)",
                "detail": (
                    f"Send <strong>{price}{period}</strong> in USD to <code>{wise}</code>. "
                    f"Reference: <code>{memo}</code>."
                ),
                "action_label": "Open Wise",
                "action_url": os.environ.get("WINNERSPY_WISE_URL", "https://wise.com/send").strip(),
                "copy": wise,
            }
        )

    usdt = os.environ.get("WINNERSPY_USDT_ADDRESS", "").strip()
    if usdt:
        network = os.environ.get("WINNERSPY_USDT_NETWORK", "TRC20").strip()
        methods.append(
            {
                "id": "usdt",
                "title": f"USDT ({network})",
                "detail": (
                    f"Send <strong>{price}{period}</strong> equivalent in USDT ({network}). "
                    f"Memo/reference: <code>{memo}</code>."
                ),
                "copy": usdt,
            }
        )

    pay_email = os.environ.get("WINNERSPY_PAYMENT_EMAIL", "").strip()
    support = upgrade_contact_url()
    if not methods:
        body = (
            f"WinnerSpy {plan.upper()} subscription ({price}{period})%0A"
            f"Account email: {email}%0A"
            f"Payment reference: {memo}"
        )
        if support.startswith("http"):
            methods.append(
                {
                    "id": "contact",
                    "title": "Get payment details",
                    "detail": payment_bank_info(),
                    "action_label": "Contact us to pay",
                    "action_url": support,
                    "primary": True,
                }
            )
        elif pay_email:
            methods.append(
                {
                    "id": "email",
                    "title": "Email payment",
                    "detail": (
                        f"{payment_bank_info()} "
                        f"Contact: <code>{pay_email}</code> — reference <code>{memo}</code>."
                    ),
                    "action_label": f"Email {pay_email}",
                    "action_url": (
                        f"mailto:{pay_email}?subject=WinnerSpy%20{plan.upper()}%20{price}{period}"
                        f"&body={body}"
                    ),
                    "primary": True,
                }
            )
        else:
            methods.append(
                {
                    "id": "manual",
                    "title": "Manual payment (USD)",
                    "detail": (
                        f"{payment_bank_info()} "
                        f"Account: <strong>{email}</strong> · Plan: <strong>{plan.upper()}</strong>."
                    ),
                }
            )

    return methods
