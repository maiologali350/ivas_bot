"""
bot/scheduler.py — Background polling loop.
Runs cloudscraper calls in a thread pool (asyncio.to_thread) since
cloudscraper is synchronous.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot

from config import POLL_INTERVAL
from db.database import is_message_seen, log_event, mark_message_seen, purge_old_events
from ivas.client import IVASClient
from bot.notifier import Notifier

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._notifier = Notifier(bot)
        self._running = False

        self._last_status: datetime = datetime.min
        self._last_balance: datetime = datetime.min
        self._last_stats: datetime = datetime.min

        self._status_every = timedelta(minutes=10)
        self._balance_every = timedelta(minutes=15)
        self._stats_every = timedelta(minutes=20)

    async def start(self) -> None:
        self._running = True
        await self._notifier.notify_startup()
        logger.info("Scheduler started — polling every %ds", POLL_INTERVAL)

        while self._running:
            try:
                await self._run_checks()
            except Exception as exc:
                logger.exception("Unexpected error in scheduler loop")
                await self._notifier.notify_error("Scheduler loop", str(exc))
            await asyncio.sleep(POLL_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        await self._notifier.notify_shutdown()

    # ── Poll cycle ────────────────────────────────────────────────────────────

    async def _run_checks(self) -> None:
        now = datetime.utcnow()

        # Create one client instance (one cookie-authenticated session) per cycle
        client = IVASClient()

        try:
            if now - self._last_status >= self._status_every:
                await self._check_status(client)
                self._last_status = now

            if now - self._last_balance >= self._balance_every:
                await self._check_balance(client)
                self._last_balance = now

            if now - self._last_stats >= self._stats_every:
                await self._check_stats(client)
                self._last_stats = now

            await self._check_new_messages(client)

        except RuntimeError as exc:
            err = str(exc)
            logger.error("IVAS error: %s", err)
            if "expired" in err.lower() or "session" in err.lower():
                await self._notifier.notify_cookie_expired()
            else:
                await self._notifier.notify_error("IVAS connection", err)
            await log_event("error", err[:200])

        await purge_old_events(days=30)

    # ── Check helpers ─────────────────────────────────────────────────────────

    async def _check_status(self, client: IVASClient) -> None:
        try:
            status = await asyncio.to_thread(client.get_account_status)
            await self._notifier.notify_status(status)
            state = "active" if status.is_active else "inactive"
            await log_event("status", f"Account {state}")
        except Exception as exc:
            logger.error("Status check failed: %s", exc)
            await self._notifier.notify_error("Status check", str(exc))

    async def _check_balance(self, client: IVASClient) -> None:
        try:
            balance = await asyncio.to_thread(client.get_balance)
            await self._notifier.notify_balance(balance)
            await log_event("balance", f"Revenue={balance.amount} {balance.currency}")
        except Exception as exc:
            logger.error("Balance check failed: %s", exc)
            await self._notifier.notify_error("Balance check", str(exc))

    async def _check_stats(self, client: IVASClient) -> None:
        try:
            stats = await asyncio.to_thread(client.get_message_stats)
            await self._notifier.notify_stats(stats)
            await log_event(
                "stats",
                f"Total={stats.total_sms} Paid={stats.paid_sms} Revenue={stats.revenue}",
            )
        except Exception as exc:
            logger.error("Stats check failed: %s", exc)
            await self._notifier.notify_error("Stats check", str(exc))

    async def _check_new_messages(self, client: IVASClient) -> None:
        try:
            messages = await asyncio.to_thread(client.get_new_messages)
            new_count = 0
            for msg in messages:
                if not await is_message_seen(msg.message_id):
                    await self._notifier.notify_new_message(msg)
                    await mark_message_seen(msg.message_id)
                    new_count += 1
            if new_count:
                await log_event("message", f"{new_count} new OTP(s) notified")
                logger.info("Notified %d new messages", new_count)
            else:
                logger.debug("No new messages")
        except Exception as exc:
            logger.error("Message check failed: %s", exc)
            await self._notifier.notify_error("Message check", str(exc))
