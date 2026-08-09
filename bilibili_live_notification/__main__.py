"""Send email notification when bilibili live start."""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Tuple

from bilibili_api import live, ResponseCodeException


from . import apprise_notify, config, emailtools, rate_limit, room, state, webhook

from collections import defaultdict, OrderedDict


def _format_time(v: datetime) -> str:
    return v.strftime("%H:%M:%S %Y-%m-%d")


LOGGER = logging.getLogger(__name__)


class _StatusConfirmation:
    """Require repeated observations before accepting a polling transition."""

    def __init__(self, current: bool, confirmations: int):
        self.current = current
        self.confirmations = max(1, confirmations)
        self._candidate = current
        self._count = 0

    def observe(self, value: bool) -> bool:
        if value == self.current:
            self._candidate = value
            self._count = 0
            return False
        if value != self._candidate:
            self._candidate = value
            self._count = 1
        else:
            self._count += 1
        if self._count < self.confirmations:
            return False
        self.current = value
        self._count = 0
        return True


def _make_status_event(room_id: str, is_live: bool) -> dict:
    now = int(time.time())
    event_type = "LIVE" if is_live else "PREPARING"
    return {
        "room_display_id": room_id,
        "room_real_id": int(room_id),
        "type": event_type,
        "data": {
            "cmd": event_type,
            "roomid": int(room_id),
            "send_time": now,
            "source": "polling",
        },
    }


async def _handle_live(event):
    rid = event["room_display_id"]

    # TODO: support template for email subject and body
    now = datetime.now()
    room_data = await room.get(rid)
    emailtools.send(
        config.get_room_email_to(rid),
        f'[开播]{room_data["name"]} - {_format_time(now)}',
        f'{room_data["url"]} ',
    )


async def _handle_view(event):
    rid = event["room_display_id"]
    room.ROOM_POPUPARITY[rid] = event["data"]


EVENT_EXAMPLE = {}


def _load_event_example():
    with open("event.example.json", encoding="utf8") as f:
        return json.load(f)


def _save_event_example():
    with open("event.example.json", "w", encoding="utf8") as f:
        json.dump(EVENT_EXAMPLE, f, ensure_ascii=False, indent=2)


try:
    EVENT_EXAMPLE = _load_event_example()
except OSError:
    pass


def _collect_event_example(event):
    event_type = event["type"]
    is_new = event_type not in EVENT_EXAMPLE
    EVENT_EXAMPLE[event_type] = event
    if is_new:
        LOGGER.info("update ./event.example.json due to new event type: %s", event_type)
        _save_event_example()


ROOM_EVENT_TIME: Dict[Tuple[str, str], float] = {}


def _throttle_event(event) -> bool:
    event_type = event["type"]
    rid = str(event["room_display_id"])
    event_time_key = (rid, event_type)
    if event_time_key in ROOM_EVENT_TIME and time.time() - ROOM_EVENT_TIME[
        event_time_key
    ] < int(config.get(f"BILIBILI_EVENT_THROTTLE_{event_type}") or "0"):
        LOGGER.info("event throttled: %s: %s", rid, event_type)
        return True
    ROOM_EVENT_TIME[event_time_key] = time.time()
    return False


ROOM_EVENT_TYPE_KEYS = defaultdict(lambda: defaultdict(OrderedDict))


def _distinct_event(event, data: dict) -> bool:
    event_type = event["type"]
    rid = str(event["room_display_id"])
    key = config.get(f"BILIBILI_EVENT_DISTINCT_KEY_{event_type}", data)
    if key == "":
        return False
    event_keys = ROOM_EVENT_TYPE_KEYS[rid][event_type]
    if key in event_keys:
        LOGGER.info(
            "skip duplicated event: %s: %s: %s",
            rid,
            event_type,
            key,
        )
        return True

    event_keys[key] = True
    limit = int(
        config.get(f"BILIBILI_EVENT_DISTINCT_LIMIT_{event_type}", data) or "128",
    )
    while len(event_keys) > limit >= 0:
        event_keys.popitem(last=False)

    return False


async def _handle_event(event, *, skip_room_data_update=False):
    event_type = event["type"]
    rid = str(event["room_display_id"])

    desired_live_state = None
    if event_type == "LIVE":
        desired_live_state = True
    elif event_type == "PREPARING":
        desired_live_state = False

    # Persistent state is the common deduplication point for websocket and
    # polling. This also prevents a container restart from re-sending LIVE.
    if desired_live_state is not None:
        previous = state.get(rid)
        if previous is not None and previous.is_live == desired_live_state:
            LOGGER.info("skip unchanged room state: %s: %s", rid, event_type)
            return

    if event_type == "LIVE":
        LOGGER.info(event)
    else:
        LOGGER.debug(event)

    _collect_event_example(event)

    # State transitions must not be throttled: a short stream followed by a
    # restart inside the old 10-minute LIVE window is still a real transition.
    if desired_live_state is None and _throttle_event(event):
        return

    # update room data cache
    if not skip_room_data_update and event_type in ("LIVE", "PREPARING", "ROOM_CHANGE"):
        room_data = await room.get(rid, max_age_secs=0)

    if event_type == "LIVE":
        await _handle_live(event)
    elif event_type == "VIEW":
        await _handle_view(event)

    room_data = await room.get(rid)
    data = {
        **dict(
            event=event,
            room=room_data,
        ),
        **dict(config.get_items(f"BILIBILI_ROOM_TEMPLATE_VAR_{rid}_")),
    }

    if _distinct_event(event, data):
        return

    await apprise_notify.trigger(event_type, data)
    await webhook.trigger_many(
        (
            config.get_csv(f"BILIBILI_ROOM_WEBHOOK_{rid}_{event_type}")
            or config.get_csv(f"BILIBILI_WEBHOOK_{event_type}")
        ),
        data,
    )

    if desired_live_state is not None:
        state.save(rid, desired_live_state, room_data.get("title", ""))
    elif event_type == "ROOM_CHANGE":
        state.update_title(rid, room_data.get("title", ""))


async def _subscribe(id: str) -> None:
    room1 = live.LiveDanmaku(id)  # type: ignore
    room1.add_event_listener("ALL", _handle_event)  # type: ignore

    while True:
        await room1.connect()
        if room1.get_status() == room1.STATUS_ESTABLISHED:
            await room1.disconnect()


async def _poll(id: str, interval_secs: int) -> None:
    persisted = state.get(id)
    tracker = None
    last_title = persisted.title if persisted else ""
    while True:
        await asyncio.sleep(0)
        try:
            data = await room.get(id, max_age_secs=0)
            ri = data["data"]["room_info"]
            is_live = ri["live_status"] == 1
            title = ri["title"]
            if tracker is None:
                if persisted is None:
                    if is_live and config.NOTIFY_ON_INITIAL_LIVE:
                        await _handle_event(
                            _make_status_event(id, True),
                            skip_room_data_update=True,
                        )
                    else:
                        state.save(id, is_live, title)
                    tracker = _StatusConfirmation(is_live, config.POLLING_CONFIRMATIONS)
                else:
                    tracker = _StatusConfirmation(
                        persisted.is_live, config.POLLING_CONFIRMATIONS
                    )

            if tracker.observe(is_live):
                await _handle_event(
                    _make_status_event(id, is_live),
                    skip_room_data_update=True,
                )
            elif last_title and title != last_title:
                await _handle_event(
                    {
                        "room_display_id": id,
                        "room_real_id": int(id),
                        "type": "ROOM_CHANGE",
                        "data": {
                            "cmd": "ROOM_CHANGE",
                            "data": {
                                "title": title,
                                "area_id": ri["area_id"],
                                "parent_area_id": ri["parent_area_id"],
                                "area_name": ri["area_name"],
                                "parent_area_name": ri["parent_area_name"],
                                "live_key": "0",
                                "sub_session_key": "",
                            },
                        },
                    },
                    skip_room_data_update=True,
                )
            last_title = title
        except ResponseCodeException as ex:
            if ex.code == -352:
                # 风控
                await asyncio.sleep(3600)
            else:
                raise
        except:
            logging.exception("error during polling")
        await asyncio.sleep(interval_secs)


async def main():
    os.environ.setdefault("BILIBILI_EVENT_THROTTLE_LIVE", "600")
    rate_limit.BILIBILI_API.set(rate_limit.RateLimiter(50, 1))

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(levelname)-6s[%(asctime)s]:%(name)s:%(lineno)d: %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
    )
    debug_logger_names = config.get_csv("DEBUG")
    for logger in [
        LOGGER,
        apprise_notify.LOGGER,
        state.LOGGER,
        webhook._LOGGER,
        room.LOGGER,
    ]:
        logger.setLevel(
            logging.DEBUG if logger.name in debug_logger_names else logging.INFO
        )
        logger.addHandler(handler)

    state.initialize()
    # Validate and report Apprise configuration during startup.
    apprise_notify._instance()
    await webhook.trigger_many(config.get_csv("SERVER_WEBHOOK_START"))
    if config.TEST_EMAIL_TO:
        LOGGER.info("发送测试邮件")
        emailtools.send(
            config.TEST_EMAIL_TO,
            f"[启动] - {_format_time(datetime.now())}",
            "服务启动测试邮件",
        )

    def jobs():
        room_ids = list(config.discover_bilibili_room_id())
        if config.POLLING_INTERVAL_SECS > 0:
            for i in room_ids:
                yield _poll(i, config.POLLING_INTERVAL_SECS)

        for i in room_ids:
            yield _subscribe(i)

    await asyncio.gather(*jobs())  # type: ignore
    LOGGER.info("未配置要监控的直播间，请查看 README.md")


if __name__ == "__main__":
    asyncio.run(main())
