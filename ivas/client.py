"""
ivas/client.py — ivasms.com client using cloudscraper (bypasses Cloudflare)
and cookie-based authentication.

Authentication:
  ivasms.com is behind Cloudflare and uses Laravel session cookies.
  There is no username/password API — you must supply the two cookies
  exported from your browser after a manual login:
    - IVAS_XSRF_TOKEN
    - IVAS_SESSION  (the ivas_sms_session cookie)

  Cookies expire in ~2 hours. When they expire you'll see a 401/redirect
  error and the bot will notify you to refresh them.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import cloudscraper
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
    before_sleep_log,
)

from config import (
    IVAS_BASE_URL,
    IVAS_XSRF_TOKEN,
    IVAS_SESSION,
    MAX_RETRIES,
    RETRY_WAIT_MIN,
    RETRY_WAIT_MAX,
)

logger = logging.getLogger(__name__)


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class AccountStatus:
    is_active: bool
    username: str = "unknown"
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class Balance:
    amount: str       # keep as string — site shows formatted value
    currency: str = "USD"
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class MessageStats:
    total_sms: str
    paid_sms: str
    unpaid_sms: str
    revenue: str
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class IncomingMessage:
    message_id: str       # phone_number used as unique ID
    sender: str           # phone number
    phone_range: str      # country range e.g. "+1"
    otp_message: str      # the actual OTP text
    received_at: str


# ── Retry decorator ───────────────────────────────────────────────────────────

def _retried(func):
    return retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_random_exponential(min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )(func)


# ── Client ────────────────────────────────────────────────────────────────────

class IVASClient:
    """
    Synchronous wrapper using cloudscraper (handles Cloudflare JS challenges).
    Runs in a thread pool from async callers via asyncio.to_thread().
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self) -> None:
        self._scraper = cloudscraper.create_scraper()
        self._scraper.headers.update(self.HEADERS)

        # Inject cookies
        self._scraper.cookies.set("XSRF-TOKEN",       IVAS_XSRF_TOKEN,   domain="www.ivasms.com")
        self._scraper.cookies.set("ivas_sms_session", IVAS_SESSION,      domain="www.ivasms.com")
        self._scraper.cookies.set("cf_clearance",     IVAS_CF_CLEARANCE, domain="www.ivasms.com")

        self._csrf_token: Optional[str] = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_csrf(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("input", {"name": "_token"})
        if tag:
            return tag.get("value")
        # Also try meta tag
        meta = soup.find("meta", {"name": "csrf-token"})
        if meta:
            return meta.get("content")
        return None

    def _check_session(self, html: str) -> bool:
        """Return False if redirected to login page."""
        return "login" not in html[:500].lower() or "portal" in html[:1000].lower()

    @_retried
    def _get(self, path: str, **kwargs) -> str:
        url = f"{IVAS_BASE_URL}{path}"
        resp = self._scraper.get(url, timeout=20, **kwargs)
        if resp.status_code == 403:
            raise RuntimeError("Cloudflare blocked — cookies may be stale or IP flagged")
        resp.raise_for_status()
        return resp.text

    @_retried
    def _post(self, path: str, data: dict, extra_headers: Optional[dict] = None) -> str:
        url = f"{IVAS_BASE_URL}{path}"
        headers = {
            "Accept": "text/html, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": IVAS_BASE_URL,
            "Referer": f"{IVAS_BASE_URL}/portal/sms/received",
        }
        if extra_headers:
            headers.update(extra_headers)
        resp = self._scraper.post(url, data=data, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.text

    def _ensure_csrf(self) -> None:
        """Fetch the portal page and grab the CSRF token if not cached."""
        if self._csrf_token:
            return
        html = self._get("/portal/sms/received")
        if not self._check_session(html):
            raise RuntimeError(
                "Session expired — cookies are no longer valid. "
                "Please refresh IVAS_XSRF_TOKEN and IVAS_SESSION in your .env."
            )
        token = self._get_csrf(html)
        if not token:
            raise RuntimeError("Could not extract CSRF token from IVAS portal page.")
        self._csrf_token = token
        logger.info("IVAS session validated, CSRF token obtained")

    # ── Public API ────────────────────────────────────────────────────────────

    def get_account_status(self) -> AccountStatus:
        self._ensure_csrf()
        html = self._get("/portal/dashboard")
        soup = BeautifulSoup(html, "html.parser")

        # Try to find username from nav/profile area
        username_tag = soup.select_one(".navbar-nav .nav-link, .user-name, #user-name")
        username = username_tag.get_text(strip=True) if username_tag else "unknown"

        is_active = "portal" in html and "login" not in html[:300].lower()
        return AccountStatus(is_active=is_active, username=username)

    def get_balance(self) -> Balance:
        self._ensure_csrf()
        html = self._get("/portal/dashboard")
        soup = BeautifulSoup(html, "html.parser")

        # Common patterns on revenue dashboards
        revenue_el = (
            soup.select_one("#RevenueSMS")
            or soup.select_one(".revenue")
            or soup.find(string=re.compile(r"\$[\d.]+"))
        )
        amount = revenue_el.get_text(strip=True) if revenue_el else "N/A"
        amount = amount.replace("USD", "").replace("$", "").strip()
        return Balance(amount=amount, currency="USD")

    def get_message_stats(self, from_date: str = "", to_date: str = "") -> MessageStats:
        self._ensure_csrf()
        html = self._post(
            "/portal/sms/received/getsms",
            data={"from": from_date, "to": to_date, "_token": self._csrf_token},
        )
        soup = BeautifulSoup(html, "html.parser")

        def _text(selector: str) -> str:
            el = soup.select_one(selector)
            return el.get_text(strip=True) if el else "0"

        return MessageStats(
            total_sms=_text("#CountSMS"),
            paid_sms=_text("#PaidSMS"),
            unpaid_sms=_text("#UnpaidSMS"),
            revenue=_text("#RevenueSMS"),
        )

    def get_new_messages(self, from_date: str = "", to_date: str = "") -> list[IncomingMessage]:
        self._ensure_csrf()
        today = datetime.now().strftime("%d/%m/%Y")
        from_date = from_date or today
        to_date = to_date or today

        # Step 1: get stats page with sms_details (country ranges)
        html = self._post(
            "/portal/sms/received/getsms",
            data={"from": from_date, "to": to_date, "_token": self._csrf_token},
        )
        soup = BeautifulSoup(html, "html.parser")
        country_ranges = []
        for item in soup.select("div.item"):
            col = item.select_one(".col-sm-4")
            if col:
                country_ranges.append(col.get_text(strip=True))

        messages = []
        for phone_range in country_ranges:
            # Step 2: get numbers in this range
            num_html = self._post(
                "/portal/sms/received/getsms/number",
                data={
                    "_token": self._csrf_token,
                    "start": from_date,
                    "end": to_date,
                    "range": phone_range,
                },
            )
            num_soup = BeautifulSoup(num_html, "html.parser")
            for card in num_soup.select("div.card.card-body"):
                num_col = card.select_one(".col-sm-4")
                if not num_col:
                    continue
                phone_number = num_col.get_text(strip=True)

                # Step 3: get OTP text for this number
                otp_html = self._post(
                    "/portal/sms/received/getsms/number/sms",
                    data={
                        "_token": self._csrf_token,
                        "start": from_date,
                        "end": to_date,
                        "Number": phone_number,
                        "Range": phone_range,
                    },
                )
                otp_soup = BeautifulSoup(otp_html, "html.parser")
                otp_el = otp_soup.select_one(".col-9.col-sm-6 p")
                otp_text = otp_el.get_text(strip=True) if otp_el else ""

                if otp_text:
                    messages.append(IncomingMessage(
                        message_id=f"{phone_range}:{phone_number}:{from_date}",
                        sender=phone_number,
                        phone_range=phone_range,
                        otp_message=otp_text,
                        received_at=datetime.now().isoformat(),
                    ))

        logger.info("Fetched %d messages for %s", len(messages), from_date)
        return messages
