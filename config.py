"""
config.py — Central configuration loaded from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Required environment variable '{key}' is not set.")
    return val


# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID: int = int(_require("TELEGRAM_CHAT_ID"))

# ── IVAS cookies ──────────────────────────────────────────────────────────────
# Export these from your browser after logging in to ivasms.com manually.
# DevTools → Application → Cookies → www.ivasms.com
IVAS_XSRF_TOKEN: str = _require("IVAS_XSRF_TOKEN")
IVAS_SESSION: str = _require("IVAS_SESSION")

IVAS_BASE_URL: str = "https://www.ivasms.com"

# ── Polling ───────────────────────────────────────────────────────────────────
POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "60"))

# ── Retry ─────────────────────────────────────────────────────────────────────
MAX_RETRIES: int = 3
RETRY_WAIT_MIN: int = 2
RETRY_WAIT_MAX: int = 10

# ── SQLite ────────────────────────────────────────────────────────────────────
DB_PATH: str = os.getenv("DB_PATH", "ivas_bot.db")
