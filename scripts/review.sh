#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
exec "${REVIEW_PYTHON:-$ROOT/.venv-review/bin/python}" -m pi05_demo.curation "$@"
