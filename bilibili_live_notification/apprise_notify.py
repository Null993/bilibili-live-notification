"""Apprise notification integration."""

import asyncio
import logging
from typing import Optional

import apprise

from . import config

LOGGER = logging.getLogger(__name__)
_INSTANCE: Optional[apprise.Apprise] = None
_LOCK: Optional[asyncio.Lock] = None


def _instance() -> apprise.Apprise:
    global _INSTANCE
    if _INSTANCE is None:
        instance = apprise.Apprise()
        for url in config.get_apprise_urls():
            if not instance.add(url):
                LOGGER.error("invalid Apprise URL (secret omitted)")
        _INSTANCE = instance
        LOGGER.info("configured %d Apprise notification target(s)", len(instance))
    return _INSTANCE


def _default_title(event_type: str, room_data: dict) -> str:
    state_name = "开播" if event_type == "LIVE" else "下播"
    return f"[B站{state_name}] {room_data['name']}"


def _default_body(event_type: str, room_data: dict) -> str:
    state_name = "已开播" if event_type == "LIVE" else "已下播"
    return "\n".join(
        (
            f"{room_data['name']} {state_name}",
            room_data.get("title", ""),
            room_data["url"],
        )
    )


async def trigger(event_type: str, data: dict) -> None:
    if event_type not in config.APPRISE_EVENTS:
        return
    instance = _instance()
    if len(instance) == 0:
        return

    room_data = data["room"]
    title = config.get(f"APPRISE_TITLE_{event_type}", data) or _default_title(
        event_type, room_data
    )
    body = config.get(f"APPRISE_BODY_{event_type}", data) or _default_body(
        event_type, room_data
    )

    global _LOCK
    if _LOCK is None:
        _LOCK = asyncio.Lock()
    async with _LOCK:
        try:
            success = await asyncio.to_thread(
                instance.notify,
                title=title,
                body=body,
                notify_type=apprise.NotifyType.INFO,
            )
            if not success:
                LOGGER.error("one or more Apprise targets rejected %s", event_type)
        except Exception:
            LOGGER.exception("Apprise notification failed: %s", event_type)
