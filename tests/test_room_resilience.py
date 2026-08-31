import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler

import pytest
from bilibili_api import ResponseCodeException

from bilibili_live_notification import config, logging_config, room


@pytest.fixture(autouse=True)
def reset_room_state():
    room._CACHE.clear()
    room._SINGLE_FLIGHT.clear()
    room._RISK_COOLDOWN_UNTIL = 0.0
    yield
    room._CACHE.clear()
    room._SINGLE_FLIGHT.clear()
    room._RISK_COOLDOWN_UNTIL = 0.0


@pytest.mark.asyncio
async def test_fetch_timeout_has_bounded_retries(monkeypatch):
    attempts = 0
    delays = []

    async def fail(_rid):
        nonlocal attempts
        attempts += 1
        raise TimeoutError

    async def no_wait(delay):
        delays.append(delay)

    monkeypatch.setattr(room, "_fetch", fail)
    monkeypatch.setattr(room.asyncio, "sleep", no_wait)
    monkeypatch.setattr(room.random, "uniform", lambda _a, _b: 1.0)
    monkeypatch.setattr(config, "API_RETRY_ATTEMPTS", 3)
    monkeypatch.setattr(config, "API_RETRY_BASE_SECS", 2.0)
    monkeypatch.setattr(config, "API_RETRY_MAX_SECS", 30.0)

    with pytest.raises(room.FetchUnavailable):
        await room.get("123", max_age_secs=0)

    assert attempts == 3
    assert delays == [2.0, 4.0]


@pytest.mark.asyncio
async def test_failed_refresh_returns_marked_cache(monkeypatch):
    room._CACHE["123"] = (
        1.0,
        {"name": "主播", "title": "旧标题", "url": "url", "popularity": 0},
    )

    async def fail(_rid):
        raise TimeoutError

    monkeypatch.setattr(room, "_fetch", fail)
    monkeypatch.setattr(config, "API_RETRY_ATTEMPTS", 1)

    result = await room.get("123", max_age_secs=0)

    assert result["title"] == "旧标题"
    assert result["_stale"] is True


@pytest.mark.asyncio
async def test_single_flight_only_refreshes_once(monkeypatch):
    attempts = 0

    async def succeed(rid):
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0)
        return {
            "name": "主播",
            "title": "标题",
            "url": f"https://live.bilibili.com/{rid}",
            "data": {},
            "popularity": 1,
        }

    monkeypatch.setattr(room, "_fetch", succeed)
    first, second = await asyncio.gather(
        room.get("123", max_age_secs=10), room.get("123", max_age_secs=10)
    )

    assert attempts == 1
    assert first is second


@pytest.mark.asyncio
async def test_risk_control_uses_cache_without_more_requests(monkeypatch):
    attempts = 0
    room._CACHE["123"] = (
        1.0,
        {"name": "主播", "title": "旧标题", "url": "url", "popularity": 0},
    )

    async def risk_controlled(_rid):
        nonlocal attempts
        attempts += 1
        raise ResponseCodeException(-352, "risk control")

    monkeypatch.setattr(room, "_fetch", risk_controlled)
    monkeypatch.setattr(config, "API_RISK_COOLDOWN_SECS", 1800)

    first = await room.get("123", max_age_secs=0)
    second = await room.get("123", max_age_secs=0)

    assert attempts == 1
    assert first["_stale"] is True
    assert second["_stale"] is True
    assert room._RISK_COOLDOWN_UNTIL > 0


def test_daily_log_handler_keeps_configured_days(tmp_path, monkeypatch):
    root = logging.getLogger()
    old_handlers = root.handlers[:]
    try:
        monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))
        monkeypatch.setattr(config, "LOG_RETENTION_DAYS", 7)
        path = logging_config.configure()
        daily = next(
            handler
            for handler in root.handlers
            if isinstance(handler, TimedRotatingFileHandler)
        )
        assert path == tmp_path / "bilibili-live-notification.log"
        assert daily.backupCount == 6
        assert daily.encoding.lower().replace("-", "") == "utf8"
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers[:] = old_handlers
