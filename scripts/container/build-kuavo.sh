#!/usr/bin/env bash
set -euo pipefail

cd /root/kuavo_ws
export ROBOT_VERSION="${ROBOT_VERSION:-62}"
CATKIN_JOBS="${CATKIN_JOBS:-4}"
CATKIN_PACKAGE_JOBS="${CATKIN_PACKAGE_JOBS:-1}"

echo "Workspace: $(pwd)"
echo "ROBOT_VERSION=$ROBOT_VERSION"
echo "CATKIN_JOBS=$CATKIN_JOBS"
echo "CATKIN_PACKAGE_JOBS=$CATKIN_PACKAGE_JOBS"

if [ "${CLEAN_BUILD:-0}" = "1" ]; then
  echo "CLEAN_BUILD=1; removing devel/ and build/ before compiling."
  rm -rf devel/ build/
fi

catkin config -DCMAKE_ASM_COMPILER=/usr/bin/as -DCMAKE_BUILD_TYPE=Release

if [ -n "${BASH_VERSION:-}" ] && [ -f installed/setup.bash ]; then
  # shellcheck disable=SC1091
  source installed/setup.bash
elif [ -n "${ZSH_VERSION:-}" ] && [ -f installed/setup.zsh ]; then
  # shellcheck disable=SC1091
  source installed/setup.zsh
elif [ -f installed/setup.bash ]; then
  # shellcheck disable=SC1091
  source installed/setup.bash
else
  echo "WARN: installed/setup.zsh and installed/setup.bash were not found."
fi

catkin build -j "$CATKIN_JOBS" -p "$CATKIN_PACKAGE_JOBS" humanoid_controllers ${EXTRA_PKGS:-}
