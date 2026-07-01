#!/usr/bin/env bash
set -euo pipefail

cd /root/kuavo_ws

if [ -n "${BASH_VERSION:-}" ] && [ -f installed/setup.bash ]; then
  # shellcheck disable=SC1091
  source installed/setup.bash
elif [ -n "${ZSH_VERSION:-}" ] && [ -f installed/setup.zsh ]; then
  # shellcheck disable=SC1091
  source installed/setup.zsh
fi

if [ -n "${BASH_VERSION:-}" ] && [ -f devel/setup.bash ]; then
  # shellcheck disable=SC1091
  source devel/setup.bash
elif [ -n "${ZSH_VERSION:-}" ] && [ -f devel/setup.zsh ]; then
  # shellcheck disable=SC1091
  source devel/setup.zsh
elif [ -f devel/setup.bash ]; then
  # shellcheck disable=SC1091
  source devel/setup.bash
else
  echo "ERROR: devel setup file was not found. Build the workspace first." >&2
  exit 1
fi

export LD_LIBRARY_PATH="/opt/drake/lib:/usr/lib:${LD_LIBRARY_PATH:-}"
export ROBOT_VERSION="${ROBOT_VERSION:-62}"

echo "NOTE: Gazebo may require building additional packages, for example: EXTRA_PKGS=gazebo_sim bash /root/kuavo_ws/scripts/container/build-kuavo.sh"

LAUNCH="${KUAVO_LAUNCH:-}"
if [ -z "$LAUNCH" ]; then
  echo "Searching available wheel/gazebo simulation launch files..."
  find src \( -name "*wheel*.launch" -o -name "*gazebo*sim*.launch" \) 2>/dev/null | sort | sed "s/^/  /" || true
  CAND="$(find src -name "*wheel*gazebo*.launch" 2>/dev/null | sort | head -1 || true)"
  if [ -n "$CAND" ]; then
    LAUNCH="$(basename "$CAND")"
  else
    LAUNCH="load_kuavo_gazebo_sim.launch"
  fi
fi

echo "ROBOT_VERSION=$ROBOT_VERSION"
echo "Using launch: $LAUNCH"
KUAVO_LAUNCH_ARGS="${KUAVO_LAUNCH_ARGS:-output_system_info:=false robot_type:=2}"
echo "Launch args: $KUAVO_LAUNCH_ARGS"
# shellcheck disable=SC2086
roslaunch humanoid_controllers "$LAUNCH" $KUAVO_LAUNCH_ARGS --screen
