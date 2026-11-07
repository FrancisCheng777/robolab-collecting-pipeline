#!/usr/bin/env bash
set -euo pipefail
REPLAY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPLAY_ROOT"
echo '需要系统开发依赖：build-essential cmake libeigen3-dev libpoco-dev（可用 sudo apt install 安装）。'
cmake -S sources/libfranka-0.9.0 -B build_sources/franka -DBUILD_TESTS=OFF -DBUILD_EXAMPLES=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build_sources/franka --target franka echo_robot_state -j2
cmake -S cpp/bridge -B build_sources/bridge -DFranka_DIR="$REPLAY_ROOT/build_sources/franka" -DCMAKE_BUILD_TYPE=Release
cmake --build build_sources/bridge --target pi05_franka_bridge -j2
mkdir -p native/rebuilt_backup
cp -a native/bin native/lib native/rebuilt_backup/
cp build_sources/bridge/pi05_franka_bridge native/bin/
cp build_sources/franka/examples/echo_robot_state native/bin/
# Newly rebuilt libfranka must resolve the target machine's Poco ABI.
rm -f native/lib/libPoco*.so.* native/lib/libfranka.so*
cp -L build_sources/franka/libfranka.so.0.9 native/lib/libfranka.so.0.9
cp -L build_sources/bridge/ruckig/libruckig.so native/lib/libruckig.so
cp -L build_sources/bridge/robotiq_sdk/libgrippers_sdk.so native/lib/libgrippers_sdk.so
.venv/bin/python scripts/update_native_manifest.py
echo '已在本机重编译；旧文件保存在 native/rebuilt_backup。数据哈希保持原值。'
