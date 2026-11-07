#!/usr/bin/env bash
set -euo pipefail
REPLAY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPLAY_ROOT"
[[ -x "$REPLAY_ROOT/.venv/bin/python" ]] || { echo '请先运行 bash setup.sh'; exit 1; }
export PYTHONPATH="$REPLAY_ROOT"
export LD_LIBRARY_PATH="$REPLAY_ROOT/native/lib"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
TASK_MODE=--execute
TASK_SPEED=0.5
while [[ $# -gt 0 ]]; do
  case "$1" in
    --inspect) TASK_MODE=; shift;;
    --mock) TASK_MODE=--mock; shift;;
    --speed) [[ $# -ge 2 ]] || { echo '--speed 后需要数值'; exit 2; }; TASK_SPEED="$2"; shift 2;;
    --help|-h) echo '用法：bash run_replay.sh [--speed 0.5] [--inspect | --mock]；默认真机回放总第153条。'; exit 0;;
    *) echo '未知参数；此入口固定为总第153条，并要求现场确认。'; exit 2;;
  esac
done
"$REPLAY_ROOT/.venv/bin/python" scripts/verify_bundle.py
TASK_FLAGS=()
if [[ -n "$TASK_MODE" ]]; then TASK_FLAGS+=("$TASK_MODE"); fi
exec "$REPLAY_ROOT/.venv/bin/python" -m pi05_demo.replay \
  --episode "$REPLAY_ROOT/data/rlt_1105_fg_2_total153.h5" --speed "$TASK_SPEED" "${TASK_FLAGS[@]}"
