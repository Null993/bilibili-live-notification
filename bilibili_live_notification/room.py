# -*- coding=UTF-8 -*-
"""live room operations."""

import asyncio
import aiohttp.client_exceptions
import contextvars
import logging
import random
import time
from collections import defaultdict
from typing import Dict, Tuple

from bilibili_api import live, ResponseCodeException

from . import config, rate_limit

LOGGER = logging.getLogger(__name__)
_RISK_COOLDOWN_UNTIL = 0.0


class FetchUnavailable(RuntimeError):
    """Room data could not be refreshed and no cached value is available."""


async def _fetch(rid: str) -> dict:
    """Get room data.

    Args:
        rid (str): room id

    Returns:
        dict: normalized data
    """
    await rate_limit.BILIBILI_API.get().wait()
    start_time = time.time()
    LOGGER.info("will fetch: id=%s", rid)
    name = config.get_room_name(rid)
    info = await asyncio.wait_for(
        live.LiveRoom(rid).get_room_info(),  # type: ignore
        timeout=config.API_TIMEOUT_SECS,
    )
    assert info, "info is None"
    url = f"https://live.bilibili.com/{rid}"
    ret = dict(
        name=name,
        title=info["room_info"]["title"],
        url=url,
        data=info,
        popularity=info["room_info"]["online"],
    )
    LOGGER.info("did fetch: id=%s elapsed=%fs", rid, time.time() - start_time)
    return ret


_CACHE: Dict[str, Tuple[float, dict]] = dict()
ROOM_POPUPARITY = defaultdict(lambda: 0)
_SINGLE_FLIGHT = defaultdict(lambda: asyncio.locks.Lock())


def _stale(rid: str, reason: str) -> dict:
    outdated = _CACHE.get(rid)
    if not outdated:
        raise FetchUnavailable(reason)
    age = time.time() - outdated[0]
    LOGGER.warning(
        "using cached room data: id=%s age=%.0fs reason=%s", rid, age, reason
    )
    ret = outdated[1]
    ret["_stale"] = True
    return ret


async def _refresh(rid: str) -> dict:
    """Refresh with bounded retry/backoff and an IP-wide risk-control cooldown."""

    global _RISK_COOLDOWN_UNTIL
    remaining = _RISK_COOLDOWN_UNTIL - time.monotonic()
    if remaining > 0:
        return _stale(rid, f"risk-control cooldown ({remaining:.0f}s remaining)")

    for attempt in range(1, config.API_RETRY_ATTEMPTS + 1):
        try:
            return await _fetch(rid)
        except ResponseCodeException as ex:
            if ex.code != -352:
                raise
            _RISK_COOLDOWN_UNTIL = time.monotonic() + config.API_RISK_COOLDOWN_SECS
            LOGGER.error(
                "Bilibili risk control (-352): pause API refreshes for %ds",
                config.API_RISK_COOLDOWN_SECS,
            )
            return _stale(rid, "Bilibili risk control (-352)")
        except (TimeoutError, aiohttp.client_exceptions.ClientError) as ex:
            if attempt >= config.API_RETRY_ATTEMPTS:
                LOGGER.error(
                    "room fetch failed after %d attempt(s): id=%s error=%s",
                    attempt,
                    rid,
                    type(ex).__name__,
                )
                return _stale(rid, type(ex).__name__)
            delay = min(
                config.API_RETRY_BASE_SECS * (2 ** (attempt - 1)),
                config.API_RETRY_MAX_SECS,
            )
            delay *= random.uniform(0.8, 1.2)
            LOGGER.warning(
                "room fetch attempt %d/%d failed: id=%s error=%s retry_in=%.1fs",
                attempt,
                config.API_RETRY_ATTEMPTS,
                rid,
                type(ex).__name__,
                delay,
            )
            await asyncio.sleep(delay)


async def get(rid: str, *, max_age_secs: float = 3600) -> dict:
    """Get room data with a ttl cache

    Args:
        rid (str): room id
        ttl (float, optional): cache time to live in seconds. Defaults to 3600.

    Returns:
        dict: room data.
    """

    rid = str(rid)
    if rid not in _CACHE or time.time() - _CACHE[rid][0] > max_age_secs:
        async with _SINGLE_FLIGHT[rid]:
            # A waiter re-checks after acquiring the lock so only one request is
            # made for the same room and a failed request cannot poison the lock.
            if rid not in _CACHE or time.time() - _CACHE[rid][0] > max_age_secs:
                refreshed = await _refresh(rid)
                if not refreshed.get("_stale"):
                    entry = (time.time(), refreshed)
                    _CACHE[rid] = entry
                    ROOM_POPUPARITY[rid] = entry[1]["popularity"]

    _, ret = _CACHE[rid]
    ret["popularity"] = ROOM_POPUPARITY[rid]
    return ret
