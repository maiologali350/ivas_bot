"""
main.py — Entry point. Starts the Telegram bot and background scheduler together.
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import TELEGRAM_BOT_TOKEN
from db.database import init_db
from bot.handlers import router
from bot.scheduler import Scheduler

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
# Quieten noisy third-party loggers
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def main() -> None:
    # ── DB init ───────────────────────────────────────────────────────────────
    await init_db()

    # ── Bot + Dispatcher ──────────────────────────────────────────────────────
    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    # ── Scheduler ─────────────────────────────────────────────────────────────
    scheduler = Scheduler(bot)

    logger.info("Starting IVAS Monitor Bot…")

    # Run polling + scheduler concurrently; cancel both on shutdown
    polling_task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=["message"])
    )
    scheduler_task = asyncio.create_task(scheduler.start())

    try:
        await asyncio.gather(polling_task, scheduler_task)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received")
    finally:
        polling_task.cancel()
        scheduler_task.cancel()
        await scheduler.stop()
        await bot.session.close()
        logger.info("Bot stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
