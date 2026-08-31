"""Persistent live-room state used to reconcile websocket and polling events."""

import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from . import config

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoomState:
    room_id: str
    is_live: bool
    title: str
    updated_at: int


def initialize() -> None:
    directory = os.path.dirname(os.path.abspath(config.STATE_DB_PATH))
    os.makedirs(directory, exist_ok=True)
    with sqlite3.connect(config.STATE_DB_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS room_state (
                room_id TEXT PRIMARY KEY,
                is_live INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL
            )
            """)
        connection.commit()
    LOGGER.info("state database ready: %s", config.STATE_DB_PATH)


def get(room_id: str) -> Optional[RoomState]:
    with sqlite3.connect(config.STATE_DB_PATH) as connection:
        row = connection.execute(
            "SELECT room_id, is_live, title, updated_at FROM room_state WHERE room_id = ?",
            (str(room_id),),
        ).fetchone()
    if row is None:
        return None
    return RoomState(
        room_id=row[0], is_live=bool(row[1]), title=row[2], updated_at=row[3]
    )


def save(room_id: str, is_live: bool, title: str = "") -> None:
    with sqlite3.connect(config.STATE_DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO room_state(room_id, is_live, title, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(room_id) DO UPDATE SET
                is_live = excluded.is_live,
                title = excluded.title,
                updated_at = excluded.updated_at
            """,
            (str(room_id), int(is_live), title, int(time.time())),
        )
        connection.commit()


def claim_transition(room_id: str, is_live: bool, title: str = "") -> bool:
    """Atomically persist a changed state and return whether this caller won.

    The transaction closes the gap between a state read and write. This makes
    websocket/polling races safe across processes or containers that share the
    same state database, not only within one asyncio event loop.
    """

    room_id = str(room_id)
    now = int(time.time())
    with sqlite3.connect(config.STATE_DB_PATH, timeout=30) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT is_live FROM room_state WHERE room_id = ?", (room_id,)
        ).fetchone()
        if row is not None and bool(row[0]) == bool(is_live):
            connection.rollback()
            return False
        connection.execute(
            """
            INSERT INTO room_state(room_id, is_live, title, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(room_id) DO UPDATE SET
                is_live = excluded.is_live,
                title = excluded.title,
                updated_at = excluded.updated_at
            """,
            (room_id, int(is_live), title, now),
        )
        connection.commit()
    return True


def update_title(room_id: str, title: str) -> None:
    previous = get(room_id)
    if previous is not None:
        save(room_id, previous.is_live, title)
