"""Create and load the persistent runtime environment file."""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOM_ID = "22747736"
DEFAULT_ENV_CONTENT = f"""# 首次启动时自动生成。修改后请重启容器。
# 变量名末尾为 B 站直播间号，值为通知中显示的名称。
BILIBILI_ROOM_NAME_{DEFAULT_ROOM_ID}=直播间{DEFAULT_ROOM_ID}

# 长连接负责实时事件，轮询负责断线兜底。
BILIBILI_POLLING_INTERVAL_SECS=60
BILIBILI_POLLING_CONFIRMATIONS=2
BILIBILI_NOTIFY_ON_INITIAL_LIVE=false

# 默认通知开播和下播；添加 Apprise URL 后生效。
APPRISE_EVENTS=LIVE,PREPARING
# APPRISE_URL_1=wecombot://企业微信机器人KEY
# APPRISE_URL_2=mailtos://用户名:SMTP授权码@qq.com/收件人@qq.com
"""


@dataclass(frozen=True)
class BootstrapResult:
    path: Path
    created: bool
    loaded: int


def _environment_path() -> Path:
    explicit = os.getenv("ENV_FILE_PATH", "").strip()
    if explicit:
        return Path(explicit)
    state_path = Path(os.getenv("STATE_DB_PATH", "/data/state.db"))
    return state_path.parent / ".env"


def _decode_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _load(path: Path) -> int:
    loaded = 0
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if not name:
            continue
        if name not in os.environ:
            os.environ[name] = _decode_value(value)
            loaded += 1
    return loaded


def ensure_and_load_env() -> BootstrapResult:
    """Create the persistent .env once, then load it without overriding env."""

    path = _environment_path()
    created = False
    auto_create = os.getenv("BILIBILI_AUTO_CREATE_ENV", "true").lower() == "true"
    if not path.exists() and auto_create:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8", newline="\n") as file:
                file.write(DEFAULT_ENV_CONTENT)
            created = True
        except FileExistsError:
            # Another process won the first-start race.
            pass
    loaded = _load(path) if path.exists() else 0
    return BootstrapResult(path=path, created=created, loaded=loaded)
