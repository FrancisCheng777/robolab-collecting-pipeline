#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT:$ROOT/runtime:$ROOT/vendor${PYTHONPATH:+:$PYTHONPATH}"
if [[ -n "${FREENECT2_LIB_DIR:-}" ]]; then
  export LD_LIBRARY_PATH="$FREENECT2_LIB_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
exec "$ROOT/.venv/bin/python" -m pi05_demo.collect "$@"
