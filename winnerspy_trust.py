"""Trust copy & support config."""
from __future__ import annotations

import os

from winnerspy_config import upgrade_contact_url


def support_zalo_url() -> str:
    """Support URL — WINNERSPY_SUPPORT_URL or WINNERSPY_UPGRADE_URL."""
    return (
        os.environ.get("WINNERSPY_SUPPORT_URL", "").strip()
        or os.environ.get("WINNERSPY_ZALO_URL", "").strip()
        or upgrade_contact_url()
    )


def support_hours() -> str:
    return os.environ.get("WINNERSPY_SUPPORT_HOURS", "9am – 9pm UTC").strip()


def beta_guarantee_text() -> str:
    return os.environ.get(
        "WINNERSPY_BETA_GUARANTEE",
        "After payment we activate Pro/VIP within 24 hours. "
        "Not activated yet? Message support with your signup email — same-day help.",
    ).strip()


def positioning_line() -> str:
    return (
        "Research winning products from Facebook Ads Library by your keywords — "
        "scored reports in minutes. A fraction of AdSpy pricing."
    )
