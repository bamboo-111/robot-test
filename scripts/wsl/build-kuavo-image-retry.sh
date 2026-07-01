#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-${HOME}/kuavo_ws_src/kuavo-ros-opensource}"
IMAGE="${KUAVO_IMAGE:-kuavo-ros-opensource:master}"
DOCKERFILE="${KUAVO_DOCKERFILE:-docker/Dockerfile}"
CONTEXT="${KUAVO_DOCKER_CONTEXT:-docker}"
MAX_ATTEMPTS="${BUILD_RETRY_ATTEMPTS:-20}"
SLEEP_SECONDS="${BUILD_RETRY_SLEEP_SECONDS:-20}"
TIMEOUT_SECONDS="${BUILD_TIMEOUT_SECONDS:-900}"
NETWORK_MODE="${BUILD_NETWORK_MODE:-host}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker CLI was not found. Install Docker Desktop and enable WSL integration." >&2
  exit 1
fi

if ! command -v timeout >/dev/null 2>&1; then
  echo "ERROR: timeout command was not found. Install coreutils in WSL." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not reachable. Start Docker Desktop and retry." >&2
  exit 1
fi

if [ ! -d "$REPO_DIR" ]; then
  echo "ERROR: Repo not found: $REPO_DIR" >&2
  exit 1
fi

cd "$REPO_DIR"

echo "Repo: $REPO_DIR"
echo "Image: $IMAGE"
echo "Dockerfile: $DOCKERFILE"
echo "Context: $CONTEXT"
echo "Attempts: $MAX_ATTEMPTS"
echo "Per-attempt timeout: ${TIMEOUT_SECONDS}s"
echo "Sleep between attempts: ${SLEEP_SECONDS}s"
echo "Network mode: $NETWORK_MODE"

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  echo ""
  echo "== docker build attempt ${attempt}/${MAX_ATTEMPTS} =="
  set +e
  timeout "$TIMEOUT_SECONDS" docker build \
    --network="$NETWORK_MODE" \
    --progress=plain \
    -t "$IMAGE" \
    -f "$DOCKERFILE" \
    "$CONTEXT"
  status=$?
  set -e

  if [ "$status" -eq 0 ]; then
    echo "Docker image build succeeded: $IMAGE"
    exit 0
  fi

  if [ "$status" -eq 124 ]; then
    echo "WARN: docker build attempt timed out after ${TIMEOUT_SECONDS}s." >&2
  else
    echo "WARN: docker build attempt failed with exit code $status." >&2
  fi

  attempt=$((attempt + 1))
  if [ "$attempt" -le "$MAX_ATTEMPTS" ]; then
    echo "Retrying after ${SLEEP_SECONDS}s. Successful Docker layers will be reused from cache."
    sleep "$SLEEP_SECONDS"
  fi
done

echo "ERROR: docker build failed after ${MAX_ATTEMPTS} attempts." >&2
exit 1

