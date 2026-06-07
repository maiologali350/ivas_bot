"""
bot/notifier.py — Sends formatted Telegram notifications to the owner's private chat.
All error text is sanitized before sending to avoid Telegram HTML parse errors.
"""

import html
import logging
from aiogram import Bot
from aiogram.enums import ParseMode
from config import TELEGRAM_CHAT_ID
from ivas.client import AccountStatus, Balance, MessageStats, IncomingMessage

logger = logging.getLogger(__name__)


def _safe(text: str, max_len: int = 300) -> str:
    """Escape HTML special chars and truncate — prevents Telegram parse errors."""
    return html.escape(str(text))[:max_len]


class Notifier:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def _send(self, text: str) -> None:
        try:
            await self._bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            logger.error("Failed to send Telegram notification: %s", exc)

    async def notify_status(self, status: AccountStatus) -> None:
        icon = "✅" if status.is_active else "🔴"
        await self._send(
            f"{icon} <b>IVAS Account Status</b>\n"
            f"• State   : {'Active ✅' if status.is_active else 'Inactive ❌'}\n"
            f"• User    : {_safe(status.username)}"
        )

    async def notify_balance(self, balance: Balance) -> None:
        await self._send(
            f"💰 <b>IVAS Balance</b>\n"
            f"• Revenue : {_safe(balance.amount)} {_safe(balance.currency)}"
        )

    async def notify_stats(self, stats: MessageStats) -> None:
        await self._send(
            f"📊 <b>Message Statistics</b>\n"
            f"• Total   : {_safe(stats.total_sms)}\n"
            f"• Paid    : {_safe(stats.paid_sms)}\n"
            f"• Unpaid  : {_safe(stats.unpaid_sms)}\n"
            f"• Revenue : {_safe(stats.revenue)} USD"
        )

    async def notify_new_message(self, msg: IncomingMessage) -> None:
        await self._send(
            f"📩 <b>New OTP Message</b>\n"
            f"• Range  : {_safe(msg.phone_range)}\n"
            f"• From   : {_safe(msg.sender)}\n"
            f"• OTP    : <code>{_safe(msg.otp_message)}</code>\n"
            f"• Time   : {_safe(msg.received_at[:19])}"
        )

    async def notify_error(self, context: str, error: str) -> None:
        await self._send(
            f"❌ <b>Error — {_safe(context)}</b>\n"
            f"<code>{_safe(error)}</code>"
        )

    async def notify_cookie_expired(self) -> None:
        await self._send(
            "⚠️ <b>IVAS Session Expired</b>\n\n"
            "Your cookies have expired (they last ~2 hours).\n\n"
            "<b>To refresh:</b>\n"
            "1. Log in at https://www.ivasms.com\n"
            "2. Open DevTools → Application → Cookies\n"
            "3. Copy <code>XSRF-TOKEN</code> → <code>IVAS_XSRF_TOKEN</code> in .env\n"
            "4. Copy <code>ivas_sms_session</code> → <code>IVAS_SESSION</code> in .env\n"
            "5. Restart the bot"
        )

    async def notify_startup(self) -> None:
        await self._send("🤖 <b>IVAS Monitor Bot started.</b> Polling your account…")

    async def notify_shutdown(self) -> None:
        await self._send("🛑 <b>IVAS Monitor Bot stopped.</b>")
