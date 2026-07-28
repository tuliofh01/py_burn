#!/usr/bin/env bash
# Build a Docker image for py_burn.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${IMAGE_NAME:-pyburn:latest}"

cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker is not installed or not on PATH" >&2
    exit 1
fi

docker build -t "$IMAGE_NAME" .

cat <<EOF
Built image: $IMAGE_NAME

Run the interactive CLI (USB access required):
  docker run --rm -it --privileged \\
    -v /dev:/dev \\
    -v /run/udev:/run/udev \\
    $IMAGE_NAME

Show help:
  docker run --rm $IMAGE_NAME -h
EOF
