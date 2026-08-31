"""Central application logging with daily retained files."""

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from . import config


def configure() -> Path:
    """Configure console and daily file logging once, returning the log path."""

    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "bilibili-live-notification.log"
    formatter = logging.Formatter(
        "%(levelname)-7s [%(asctime)s] %(name)s:%(lineno)d: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    daily = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        # The active file is today, so retain at most N-1 rotated files.
        backupCount=max(1, config.LOG_RETENTION_DAYS - 1),
        encoding="utf-8",
        delay=True,
    )
    daily.suffix = "%Y-%m-%d"
    daily.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(daily)

    for name in config.get_csv("DEBUG"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    return log_path
