#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT:$ROOT/runtime"
# Keep camera/control dependencies separate from the offline export environment.
exec "${LEROBOT_PYTHON:-$ROOT/.venv-lerobot/bin/python}" -m pi05_demo.export "$@"
