import importlib

import pytest

from bilibili_live_notification import config, state
from bilibili_live_notification.__main__ import (
    _StatusConfirmation,
    _make_status_event,
)

app = importlib.import_module("bilibili_live_notification.__main__")


def test_status_confirmation_requires_stable_observations():
    tracker = _StatusConfirmation(False, confirmations=2)

    assert tracker.observe(True) is False
    assert tracker.observe(False) is False
    assert tracker.observe(True) is False
    assert tracker.observe(True) is True
    assert tracker.current is True
    assert tracker.observe(False) is False
    assert tracker.observe(False) is True
    assert tracker.current is False


def test_offline_polling_event_uses_preparing():
    event = _make_status_event("123", False)

    assert event["type"] == "PREPARING"
    assert event["data"]["source"] == "polling"
    assert event["room_display_id"] == "123"


def test_live_polling_event_uses_live():
    assert _make_status_event("456", True)["type"] == "LIVE"


@pytest.mark.asyncio
async def test_persistent_state_deduplicates_websocket_and_polling(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(config, "STATE_DB_PATH", str(tmp_path / "state.db"))
    state.initialize()
    notifications = []

    async def fake_room_get(room_id, **kwargs):
        return {
            "name": "主播",
            "title": "测试直播",
            "url": f"https://live.bilibili.com/{room_id}",
            "data": {"room_info": {"live_status": 1}},
            "popularity": 0,
        }

    async def fake_apprise(event_type, data):
        notifications.append(event_type)

    async def fake_webhooks(names, data=None):
        return None

    async def fake_live_email(event):
        return None

    monkeypatch.setattr(app, "_collect_event_example", lambda event: None)
    monkeypatch.setattr(app.room, "get", fake_room_get)
    monkeypatch.setattr(app.apprise_notify, "trigger", fake_apprise)
    monkeypatch.setattr(app.webhook, "trigger_many", fake_webhooks)
    monkeypatch.setattr(app, "_handle_live", fake_live_email)

    live_event = _make_status_event("123", True)
    await app._handle_event(live_event, skip_room_data_update=True)
    await app._handle_event(live_event, skip_room_data_update=True)
    await app._handle_event(
        _make_status_event("123", False), skip_room_data_update=True
    )

    assert notifications == ["LIVE", "PREPARING"]
    current = state.get("123")
    assert current is not None
    assert current.is_live is False
