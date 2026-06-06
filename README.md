# WinnerSpy (spywinner)

Facebook Ads Library product research — web SaaS with Free / Pro / VIP plans.

## Quick start (Windows)

```bat
start_chrome_debug.bat
start_web.bat
```

Open http://127.0.0.1:5050 — dev login: `admin@local` / `admin123`

## Stack

- Python 3 + Flask (`web_app.py`)
- Scraper/scoring pipeline (`r.py`)
- SQLite (`data/winnerspy.db`, gitignored)

## Config (env)

See `.env.example` if present, or set:

- `WINNERSPY_PAYPAL_ME` / `WINNERSPY_PAYPAL_EMAIL` — checkout
- `WINNERSPY_CHECKOUT_URL_PRO` / `WINNERSPY_CHECKOUT_URL_VIP` — Stripe/Gumroad links
- `WINNERSPY_PRODUCTION=1` + `WINNERSPY_SECRET` + `WINNERSPY_ADMIN_PASSWORD` on server

## License

Private project — all rights reserved.
