"""
bot/handlers.py — Telegram command handlers, all gated to TELEGRAM_CHAT_ID.
"""

import asyncio
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import TELEGRAM_CHAT_ID
from ivas.client import IVASClient
from bot.notifier import Notifier

logger = logging.getLogger(__name__)
router = Router()


def _owner_only(message: Message) -> bool:
    return message.chat.id == TELEGRAM_CHAT_ID


def _deny(message: Message) -> None:
    logger.warning(
        "Unauthorised access from chat_id=%s user_id=%s",
        message.chat.id,
        message.from_user.id if message.from_user else "?",
    )


@router.message(Command("start", "help"))
async def cmd_start(message: Message) -> None:
    if not _owner_only(message):
        return _deny(message)
    await message.answer(
        "🤖 <b>IVAS Monitor Bot</b>\n\n"
        "/status   — Account status\n"
        "/balance  — Revenue balance\n"
        "/stats    — Message statistics\n"
        "/messages — Today's OTP messages\n"
        "/help     — Show this help",
        parse_mode="HTML",
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not _owner_only(message):
        return _deny(message)
    notifier = Notifier(message.bot)
    try:
        client = IVASClient()
        status = await asyncio.to_thread(client.get_account_status)
        await notifier.notify_status(status)
    except Exception as exc:
        await notifier.notify_error("Status command", str(exc))


@router.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    if not _owner_only(message):
        return _deny(message)
    notifier = Notifier(message.bot)
    try:
        client = IVASClient()
        balance = await asyncio.to_thread(client.get_balance)
        await notifier.notify_balance(balance)
    except Exception as exc:
        await notifier.notify_error("Balance command", str(exc))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not _owner_only(message):
        return _deny(message)
    notifier = Notifier(message.bot)
    try:
        client = IVASClient()
        stats = await asyncio.to_thread(client.get_message_stats)
        await notifier.notify_stats(stats)
    except Exception as exc:
        await notifier.notify_error("Stats command", str(exc))


@router.message(Command("messages"))
async def cmd_messages(message: Message) -> None:
    if not _owner_only(message):
        return _deny(message)
    notifier = Notifier(message.bot)
    await message.answer("🔍 Fetching today's messages…")
    try:
        client = IVASClient()
        msgs = await asyncio.to_thread(client.get_new_messages)
        if msgs:
            for msg in msgs[:10]:
                await notifier.notify_new_message(msg)
        else:
            await message.answer("📭 No OTP messages found for today.")
    except Exception as exc:
        await notifier.notify_error("Messages command", str(exc))
