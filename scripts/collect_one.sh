#!/usr/bin/env bash
set -euo pipefail
COLLECTION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ $# -le 1 ]] || { echo 'usage: collect_one.sh [--execute|--inspect]'; exit 2; }
COLLECTION_MODE="${1:---execute}"
case "$COLLECTION_MODE" in --execute|--inspect) ;; *) echo 'mode: --execute | --inspect'; exit 2;; esac
# Compatibility entry: the terminal now stays open for r/e/s/d cycles until q.
exec "$COLLECTION_ROOT/scripts/collect_session.sh" "$COLLECTION_MODE"
