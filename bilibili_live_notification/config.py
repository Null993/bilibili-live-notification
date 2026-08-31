"""application config."""

import json
import os
from datetime import datetime
from typing import Iterator, Optional, Tuple

import jinja2


class _ChainableDebugUndefined(jinja2.ChainableUndefined, jinja2.DebugUndefined):
    pass


def get(name: str, data: Optional[dict] = None) -> str:
    """get string config

    Args:
        name (str): env var name
        data (Optional[dict], optional): template variables. Defaults to None.

    Returns:
        str: rendered config value
    """

    value = os.getenv(name) or ""
    var_prefix = "TEMPLATE_VAR_"
    if name.startswith(var_prefix):
        return value
    return jinja2.Template(
        value,
        undefined=_ChainableDebugUndefined,
    ).render(
        **{
            **dict(datetime=datetime),
            **dict(get_items(var_prefix, data)),
            **(data or {}),
        },
    )


def parse_csv(v: Optional[str]) -> list:
    """parse comma separated values.

    Args:
        v (Optional[str]): value

    Returns:
        list: values
    """
    return [i for i in (v or "").split(",") if i]


def get_csv(name: str, data: Optional[dict] = None) -> list:
    """get csv config

    Args:
        name (str): env var name
        data (Optional[dict], optional): template variables. Defaults to None.

    Returns:
        list: values
    """
    return parse_csv(get(name, data))


def get_items(prefix: str, data: Optional[dict] = None) -> Iterator[Tuple[str, str]]:
    """get room id from env vars that has BILIBILI_ROOM_NAME_ prefix

    Yields:
        Iterator[str]: room ids.
    """
    for i in os.environ.keys():
        if i.startswith(prefix):
            yield i[len(prefix) :], get(i, data)


EMAIL_FROM = get("EMAIL_FROM") or "bilibili-live-notification@noreply.github.com"
EMAIL_HOST = get("EMAIL_HOST") or "smtp.qq.com"
EMAIL_PORT = int(get("EMAIL_PORT") or "465")
EMAIL_USER = get("EMAIL_USER") or "example@qq.com"
EMAIL_PASSWORD = get("EMAIL_PASSWORD") or "<email password>"
EMAIL_TO = parse_csv(get("EMAIL_TO"))
TEST_EMAIL_TO = parse_csv(get("TEST_EMAIL_TO"))
BILIBILI_EMAIL_THROTTLE = int(get("BILIBILI_EMAIL_THROTTLE") or "600")
POLLING_INTERVAL_SECS = int(get("BILIBILI_POLLING_INTERVAL_SECS") or "0")
POLLING_CONFIRMATIONS = max(1, int(get("BILIBILI_POLLING_CONFIRMATIONS") or "2"))
NOTIFY_ON_INITIAL_LIVE = get("BILIBILI_NOTIFY_ON_INITIAL_LIVE").lower() == "true"
STATE_DB_PATH = get("STATE_DB_PATH") or "/data/state.db"
APPRISE_EVENTS = set(get_csv("APPRISE_EVENTS") or ["LIVE", "PREPARING"])
API_TIMEOUT_SECS = max(1.0, float(get("BILIBILI_API_TIMEOUT_SECS") or "15"))
API_RETRY_ATTEMPTS = max(1, int(get("BILIBILI_API_RETRY_ATTEMPTS") or "3"))
API_RETRY_BASE_SECS = max(0.1, float(get("BILIBILI_API_RETRY_BASE_SECS") or "2"))
API_RETRY_MAX_SECS = max(
    API_RETRY_BASE_SECS, float(get("BILIBILI_API_RETRY_MAX_SECS") or "30")
)
API_RISK_COOLDOWN_SECS = max(60, int(get("BILIBILI_API_RISK_COOLDOWN_SECS") or "1800"))
API_RATE_LIMIT_BURST = max(1.0, float(get("BILIBILI_API_RATE_LIMIT_BURST") or "2"))
API_RATE_LIMIT_PER_SECOND = max(
    0.01, float(get("BILIBILI_API_RATE_LIMIT_PER_SECOND") or "1")
)
APPRISE_TIMEOUT_SECS = max(1.0, float(get("APPRISE_TIMEOUT_SECS") or "30"))
LOG_DIR = get("LOG_DIR") or "/data/logs"
LOG_RETENTION_DAYS = max(1, int(get("LOG_RETENTION_DAYS") or "7"))


def get_apprise_urls() -> list:
    """Return Apprise URLs without forcing secrets into one CSV value.

    APPRISE_URLS accepts a JSON array or one URL per line. Numbered variables
    (APPRISE_URL_1, APPRISE_URL_2, ...) are also supported and are convenient
    in NAS container UIs.
    """

    value = os.getenv("APPRISE_URLS", "").strip()
    urls = []
    if value:
        if value.startswith("["):
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError("APPRISE_URLS JSON value must be an array")
            urls.extend(str(item).strip() for item in parsed)
        else:
            urls.extend(line.strip() for line in value.splitlines())

    numbered = sorted(
        (
            (int(name[len("APPRISE_URL_") :]), raw_value.strip())
            for name, raw_value in os.environ.items()
            if name.startswith("APPRISE_URL_") and name[len("APPRISE_URL_") :].isdigit()
        ),
        key=lambda item: item[0],
    )
    urls.extend(value for _, value in numbered)
    return [url for url in urls if url]


def discover_bilibili_room_id() -> Iterator[str]:
    """get room id from env vars that has BILIBILI_ROOM_NAME_ prefix

    Yields:
        Iterator[str]: room ids.
    """
    prefix = "BILIBILI_ROOM_NAME_"
    for i in os.environ.keys():
        if i.startswith(prefix):
            yield i[len(prefix) :]


def get_room_name(room_display_id: str) -> str:
    """try return `BILIBILI_ROOM_NAME_{id}` config , and fallback to id itself.

    Args:
        room_display_id (str): Room display id

    Returns:
        str: NAME config for this room.
    """

    return os.getenv(f"BILIBILI_ROOM_NAME_{room_display_id}") or room_display_id


def get_room_email_to(room_display_id: str) -> list:
    """try return `BILIBILI_ROOM_EMAIL_TO_{id}` config , and fallback to EMAIL_TO.

    Args:
        room_display_id (str): Room display id

    Returns:
        list: EMAIL_TO config for this room.
    """

    return parse_csv(get(f"BILIBILI_ROOM_EMAIL_TO_{room_display_id}")) or EMAIL_TO
