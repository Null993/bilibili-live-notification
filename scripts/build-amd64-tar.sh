#!/usr/bin/env sh
set -eu

IMAGE="${IMAGE:-bilibili-live-notification-apprise:latest}"
OUTPUT="${OUTPUT:-dist/bilibili-live-notification-apprise-amd64.tar}"
PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

mkdir -p "$(dirname -- "$PROJECT_ROOT/$OUTPUT")"
docker build --platform linux/amd64 --tag "$IMAGE" "$PROJECT_ROOT"
docker image inspect "$IMAGE" --format '{{.Architecture}}/{{.Os}}'
docker save --output "$PROJECT_ROOT/$OUTPUT" "$IMAGE"
sha256sum "$PROJECT_ROOT/$OUTPUT"
