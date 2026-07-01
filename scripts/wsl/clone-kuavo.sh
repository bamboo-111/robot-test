#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${KUAVO_WORKDIR:-${HOME}/kuavo_ws_src}"
REPO_URL="${KUAVO_REPO_URL:-https://gitcode.com/OpenLET/kuavo-ros-opensource.git}"
BRANCH="${KUAVO_BRANCH:-master}"
REPO_NAME="${KUAVO_REPO_NAME:-kuavo-ros-opensource}"
REPO_DIR="${WORKDIR}/${REPO_NAME}"

case "$WORKDIR" in
  /mnt/c/*|/mnt/d/*|/mnt/e/*|/mnt/*)
    echo "ERROR: WORKDIR is under /mnt. Put Kuavo in the WSL ext4 filesystem, for example: ~/kuavo_ws_src" >&2
    exit 1
    ;;
esac

mkdir -p "$WORKDIR"
cd "$WORKDIR"

if [ ! -d "$REPO_DIR/.git" ]; then
  git clone "$REPO_URL" "$REPO_NAME"
fi

cd "$REPO_DIR"
git fetch --all --prune
git checkout "$BRANCH"
if ! git pull --ff-only; then
  echo "WARN: git pull --ff-only failed. Local changes may exist; continuing with current checkout." >&2
fi

echo "Repo ready: $(pwd)"
echo "Branch: $(git rev-parse --abbrev-ref HEAD)"
echo "Commit: $(git rev-parse --short HEAD)"

echo "--- docker/ content ---"
ls -la docker/ 2>/dev/null || echo "No docker/ directory found."

echo "--- available sim launch files ---"
find . -name "*sim*.launch" 2>/dev/null | sort | head -50 || true

