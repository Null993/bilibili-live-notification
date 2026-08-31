import json

from bilibili_live_notification import config


def test_apprise_urls_support_json_and_numbered_variables(monkeypatch):
    monkeypatch.setenv(
        "APPRISE_URLS",
        json.dumps(
            [
                "wecombot://first",
                "mailtos://user:pass@example.com",
                "wecombot://numbered-first",
            ]
        ),
    )
    monkeypatch.setenv("APPRISE_URL_2", "json://second.example.com")
    monkeypatch.setenv("APPRISE_URL_1", "wecombot://numbered-first")

    assert config.get_apprise_urls() == [
        "wecombot://first",
        "mailtos://user:pass@example.com",
        "wecombot://numbered-first",
        "json://second.example.com",
    ]


def test_apprise_urls_remove_exact_duplicates(monkeypatch):
    monkeypatch.setenv("APPRISE_URLS", "wecombot://same\nmailtos://same")
    monkeypatch.setenv("APPRISE_URL_1", "wecombot://same")
    monkeypatch.setenv("APPRISE_URL_2", "mailtos://same")

    assert config.get_apprise_urls() == ["wecombot://same", "mailtos://same"]


def test_apprise_urls_support_multiline(monkeypatch):
    monkeypatch.setenv("APPRISE_URLS", "wecombot://one\n\nwecombot://two")
    monkeypatch.delenv("APPRISE_URL_1", raising=False)
    monkeypatch.delenv("APPRISE_URL_2", raising=False)

    assert config.get_apprise_urls() == ["wecombot://one", "wecombot://two"]
