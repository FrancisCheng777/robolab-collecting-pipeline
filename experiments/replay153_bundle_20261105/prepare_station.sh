#!/usr/bin/env bash
set -euo pipefail
REPLAY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec sudo /usr/bin/python3 "$REPLAY_ROOT/scripts/prepare_station.py" --apply "$@"
