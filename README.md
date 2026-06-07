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

## Deploy web (Render + domain)

WinnerSpy is a **Flask app** — use **[Render](https://render.com)**, not Netlify.

1. Push repo to GitHub (`ttruong0208/spywinner`)
2. Render → **New Web Service** → connect repo
3. **Build:** `pip install -r requirements-web.txt`
4. **Start:** `gunicorn web_app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
5. Set env vars (Dashboard → Environment):

```
WINNERSPY_SECRET=random-32-chars-or-more
WINNERSPY_ADMIN_PASSWORD=your-strong-admin-password
WINNERSPY_ADMIN_PATH=cp-winnerspy
WINNERSPY_ADMIN_IPS=YOUR.HOME.IP.ADDRESS
WINNERSPY_PRODUCTION=1
WINNERSPY_ALLOW_REGISTER=1
WINNERSPY_APP_URL=https://winnerspy.app
WINNERSPY_PAYPAL_ME=your-paypal-me
```

6. Render → **Settings → Custom Domains** → add `winnerspy.app`
7. Namecheap → **Advanced DNS** → add records Render shows (usually CNAME)

Facebook scan on cloud needs a **VPS with Chrome** later (`WINNERSPY_SAAS_MODE=1`). Landing, signup, checkout work on Render alone.

## License

Private project — all rights reserved.
