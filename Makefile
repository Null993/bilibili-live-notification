.PHONY: default lint format

default: format

lint:
	python3 -m black -t py312 --check --diff bilibili_live_notification/__main__.py bilibili_live_notification/config.py bilibili_live_notification/apprise_notify.py bilibili_live_notification/state.py tests
	python3 -m pytest -q

format:
	python3 -m black -t py312 bilibili_live_notification/__main__.py bilibili_live_notification/config.py bilibili_live_notification/apprise_notify.py bilibili_live_notification/state.py tests
