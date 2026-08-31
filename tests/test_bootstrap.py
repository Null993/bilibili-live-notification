from bilibili_live_notification import bootstrap


def test_first_start_generates_default_room_and_loads_it(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    room_variable = f"BILIBILI_ROOM_NAME_{bootstrap.DEFAULT_ROOM_ID}"
    monkeypatch.setenv("ENV_FILE_PATH", str(path))
    monkeypatch.setenv("BILIBILI_AUTO_CREATE_ENV", "true")
    monkeypatch.delenv(room_variable, raising=False)
    monkeypatch.delenv("BILIBILI_POLLING_INTERVAL_SECS", raising=False)
    monkeypatch.delenv("BILIBILI_POLLING_CONFIRMATIONS", raising=False)
    monkeypatch.delenv("BILIBILI_NOTIFY_ON_INITIAL_LIVE", raising=False)
    monkeypatch.delenv("APPRISE_EVENTS", raising=False)
    for name in (
        "BILIBILI_API_TIMEOUT_SECS",
        "BILIBILI_API_RETRY_ATTEMPTS",
        "BILIBILI_API_RETRY_BASE_SECS",
        "BILIBILI_API_RETRY_MAX_SECS",
        "BILIBILI_API_RISK_COOLDOWN_SECS",
        "BILIBILI_API_RATE_LIMIT_BURST",
        "BILIBILI_API_RATE_LIMIT_PER_SECOND",
        "LOG_DIR",
        "LOG_RETENTION_DAYS",
        "APPRISE_TIMEOUT_SECS",
    ):
        monkeypatch.delenv(name, raising=False)

    result = bootstrap.ensure_and_load_env()

    assert result.created is True
    assert result.path == path
    assert path.exists()
    assert "BILIBILI_ROOM_NAME_22747736=直播间22747736" in path.read_text(
        encoding="utf-8"
    )
    assert result.loaded == 15
    assert bootstrap.os.environ[room_variable] == "直播间22747736"
    assert bootstrap.os.environ["BILIBILI_POLLING_INTERVAL_SECS"] == "60"


def test_existing_environment_has_priority_over_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "BILIBILI_ROOM_NAME_22747736=文件名称\nCUSTOM_SETTING='quoted value'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE_PATH", str(path))
    monkeypatch.setenv("BILIBILI_ROOM_NAME_22747736", "外部环境名称")
    monkeypatch.delenv("CUSTOM_SETTING", raising=False)

    result = bootstrap.ensure_and_load_env()

    assert result.created is False
    assert result.loaded == 1
    assert bootstrap.os.environ["BILIBILI_ROOM_NAME_22747736"] == "外部环境名称"
    assert bootstrap.os.environ["CUSTOM_SETTING"] == "quoted value"


def test_auto_creation_can_be_disabled(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.setenv("ENV_FILE_PATH", str(path))
    monkeypatch.setenv("BILIBILI_AUTO_CREATE_ENV", "false")

    result = bootstrap.ensure_and_load_env()

    assert result.created is False
    assert result.loaded == 0
    assert not path.exists()
