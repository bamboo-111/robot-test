#!/usr/bin/env bash
set -euo pipefail

echo "DISPLAY=${DISPLAY:-}"
echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}"
echo "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-}"
echo "PULSE_SERVER=${PULSE_SERVER:-}"

ls -la /tmp/.X11-unix 2>/dev/null || echo "No /tmp/.X11-unix found."
ls -la /mnt/wslg 2>/dev/null || echo "No /mnt/wslg found."

if command -v glxinfo >/dev/null 2>&1; then
  glxinfo -B 2>/dev/null | grep -Ei "renderer|version" || true
else
  echo "glxinfo was not found. Install mesa-utils if OpenGL renderer verification is needed."
fi

if command -v xeyes >/dev/null 2>&1; then
  exec xeyes
elif command -v rviz >/dev/null 2>&1; then
  exec rviz
elif command -v gazebo >/dev/null 2>&1; then
  exec gazebo
else
  echo "No xeyes, rviz, or gazebo command was found; GUI popup test cannot be run."
fi

