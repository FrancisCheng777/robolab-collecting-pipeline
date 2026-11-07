#!/usr/bin/env bash
set -euo pipefail
REPLAY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPLAY_ROOT"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || { echo '此包适用于 Ubuntu x86_64'; exit 1; }
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -c 'import sys; assert (3,10)<=sys.version_info[:2]<=(3,12), "请使用 Python 3.10–3.12（Ubuntu 24.04 默认 3.12）"'
if [[ ! -x .venv/bin/python ]]; then "$PYTHON_BIN" -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
chmod +x native/bin/*
export LD_LIBRARY_PATH="$REPLAY_ROOT/native/lib"
ldd native/bin/pi05_franka_bridge > native/ldd_check.txt
if grep -q 'not found' native/ldd_check.txt; then cat native/ldd_check.txt; exit 1; fi
.venv/bin/python scripts/verify_bundle.py
echo '安装完成。bash run_replay.sh --inspect 只读检查；bash prepare_station.sh 准备主机；bash run_replay.sh 真机回放。'
