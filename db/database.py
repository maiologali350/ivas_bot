"""
db/database.py — Async SQLite layer for event logs and seen-message tracking.
Only metadata is stored; no message bodies or credentials.
"""

import aiosqlite
import logging
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Create tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT    NOT NULL,   -- 'status'|'balance'|'message'|'error'
                summary     TEXT    NOT NULL,   -- short human-readable summary (no PII)
                created_at  TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seen_messages (
                message_id  TEXT PRIMARY KEY,   -- IVAS message ID
                received_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_log_created
            ON event_log (created_at)
        """)
        await db.commit()
    logger.info("Database initialised at %s", DB_PATH)


async def log_event(event_type: str, summary: str) -> None:
    """Append an event to the log (no credentials, no message content)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO event_log (event_type, summary, created_at) VALUES (?, ?, ?)",
            (event_type, summary, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def is_message_seen(message_id: str) -> bool:
    """Return True if we have already notified about this IVAS message."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM seen_messages WHERE message_id = ?", (message_id,)
        ) as cur:
            return await cur.fetchone() is not None


async def mark_message_seen(message_id: str) -> None:
    """Record that we have notified about this IVAS message."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO seen_messages (message_id, received_at) VALUES (?, ?)",
            (message_id, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def purge_old_events(days: int = 30) -> None:
    """Delete event logs older than `days` days to avoid unbounded growth."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM event_log WHERE created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await db.commit()
