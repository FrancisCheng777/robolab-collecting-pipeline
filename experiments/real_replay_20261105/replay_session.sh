#!/usr/bin/env bash
set -euo pipefail
REPLAY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPLAY_ROOT"
export PYTHONPATH="$REPLAY_ROOT" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
exec env -u LD_LIBRARY_PATH "$REPLAY_ROOT/.venv/bin/python" -m pi05_demo.replay_menu "$@"
