# IVAS Monitor Bot

Monitors your ivasms.com account and sends OTP messages, stats, and balance
to your private Telegram chat. Uses `cloudscraper` to handle Cloudflare,
and cookie-based auth (no username/password API exists).

---

## Quick Start

### 1. Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Get your cookies (required — do this first)

ivasms.com has no API. Authentication uses browser session cookies.

1. Open Chrome/Firefox → log in at https://www.ivasms.com
2. Press F12 → **Application** tab → **Cookies** → `https://www.ivasms.com`
3. Copy:
   - `XSRF-TOKEN` → paste as `IVAS_XSRF_TOKEN`
   - `ivas_sms_session` → paste as `IVAS_SESSION`

> ⚠️ Cookies expire in ~2 hours. The bot will send you a Telegram notification
> when they expire with instructions to refresh them.

### 3. Configure `.env`

```bash
cp .env.example .env
# Edit .env with your values
```

```env
TELEGRAM_BOT_TOKEN=7123456789:AAH...
TELEGRAM_CHAT_ID=123456789
IVAS_XSRF_TOKEN=eyJpdiI6...
IVAS_SESSION=eyJpdiI6...
POLL_INTERVAL=60
```

### 4. Run

```bash
python main.py
```

---

## Commands

| Command | What it does |
|---|---|
| `/status` | Account active/inactive |
| `/balance` | Revenue balance |
| `/stats` | Today's SMS count, paid, unpaid, revenue |
| `/messages` | Today's OTP messages (up to 10) |

---

## Poll schedule

| Check | Frequency |
|---|---|
| Account status | Every 10 min |
| Balance | Every 15 min |
| Message stats | Every 20 min |
| New OTPs | Every poll cycle (default 60s) |

---

## Refreshing cookies

When you see this notification:
> ⚠️ IVAS Session Expired

1. Log in at https://www.ivasms.com
2. DevTools → Application → Cookies → copy the two values
3. Update `.env`
4. `Ctrl+C` then `python main.py` again

Or automate it by setting a cron job that exports cookies from a headless browser session.

---

## Security

- Only `TELEGRAM_CHAT_ID` can trigger commands
- Cookies stored only in `.env` (add to `.gitignore`)
- SQLite logs metadata only — no OTP content, no cookies
- Logs auto-purged after 30 days
