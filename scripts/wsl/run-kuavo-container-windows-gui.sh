#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-${HOME}/kuavo_ws_src/kuavo-ros-opensource}"
DEPLOY_REPO_DIR="${DEPLOY_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
IMAGE="${KUAVO_IMAGE:-kuavo-ros-opensource:master}"
CONTAINER="${KUAVO_CONTAINER:-kuavo5w_sim}"
ROBOT_VERSION="${ROBOT_VERSION:-62}"
SHELL_IN_CONTAINER="${SHELL_IN_CONTAINER:-zsh}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker CLI was not found. Install Docker Desktop for Windows and enable WSL integration." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not reachable. Start Docker Desktop and ensure WSL integration is enabled." >&2
  exit 1
fi

if [ ! -d "$REPO_DIR" ]; then
  echo "ERROR: Repo not found: $REPO_DIR" >&2
  echo "Run: bash scripts/wsl/clone-kuavo.sh" >&2
  exit 1
fi

if [ ! -d "$DEPLOY_REPO_DIR/scripts/container" ]; then
  echo "ERROR: Deployment scripts not found under: $DEPLOY_REPO_DIR/scripts/container" >&2
  exit 1
fi

echo "Repo: $REPO_DIR"
echo "Deployment scripts: $DEPLOY_REPO_DIR"
echo "Image: $IMAGE"
echo "Container: $CONTAINER"
echo "ROBOT_VERSION: $ROBOT_VERSION"
echo "DISPLAY=${DISPLAY:-}"
echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}"
echo "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-}"
echo "PULSE_SERVER=${PULSE_SERVER:-}"

if [ -f "$REPO_DIR/docker/run.sh" ]; then
  echo "NOTE: official docker/run.sh exists. Compare its mounts/devices with this Windows GUI launcher if hardware access is needed."
fi

if [ ! -d /mnt/wslg ]; then
  echo "WARN: /mnt/wslg was not found. This is expected on Windows 10 or non-WSLg sessions; GUI support may require VcXsrv/Xming."
fi

GPU_ARGS=()
if [ -e /dev/dxg ]; then
  GPU_ARGS=(
    --device=/dev/dxg
    -v /usr/lib/wsl:/usr/lib/wsl:ro
    -e LD_LIBRARY_PATH=/usr/lib/wsl/lib
    --gpus all
  )
  echo "Detected /dev/dxg; WSLg vGPU arguments enabled."
else
  echo "WARN: /dev/dxg was not found. GUI may still work, but OpenGL may use software rendering."
fi

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

docker run -it \
  --name "$CONTAINER" \
  --net host --ipc host --privileged \
  --ulimit rtprio=99 --cap-add=sys_nice --group-add=dialout \
  -e ROBOT_VERSION="$ROBOT_VERSION" \
  -e DISPLAY="${DISPLAY:-:0}" \
  -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
  -e XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/mnt/wslg/runtime-dir}" \
  -e PULSE_SERVER="${PULSE_SERVER:-unix:/mnt/wslg/PulseServer}" \
  -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v /mnt/wslg:/mnt/wslg \
  -v /dev:/dev \
  -v "$HOME/.ros:/root/.ros" \
  -v "$HOME/.config/lejuconfig:/root/.config/lejuconfig" \
  -v "$REPO_DIR:/root/kuavo_ws" \
  -v "$DEPLOY_REPO_DIR:/root/kuavo_deploy:ro" \
  "${GPU_ARGS[@]}" \
  "$IMAGE" \
  "$SHELL_IN_CONTAINER"
