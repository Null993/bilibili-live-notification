from bilibili_live_notification import config, state


def test_state_round_trip(tmp_path, monkeypatch):
    database = tmp_path / "state.db"
    monkeypatch.setattr(config, "STATE_DB_PATH", str(database))

    state.initialize()
    assert state.get("123") is None

    state.save("123", True, "first title")
    current = state.get("123")
    assert current is not None
    assert current.room_id == "123"
    assert current.is_live is True
    assert current.title == "first title"

    state.save("123", False, "last title")
    current = state.get("123")
    assert current is not None
    assert current.is_live is False
    assert current.title == "last title"


def test_update_title_preserves_live_state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DB_PATH", str(tmp_path / "state.db"))
    state.initialize()
    state.save("123", True, "old")

    state.update_title("123", "new")

    current = state.get("123")
    assert current is not None
    assert current.is_live is True
    assert current.title == "new"
