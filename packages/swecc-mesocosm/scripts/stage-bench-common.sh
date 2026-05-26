#!/usr/bin/env sh
# Copy bench_common into this package tree for hatch wheels (PyPI + local build).
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$(cd "$ROOT/../../services/bench/common/bench_common" && pwd)"
DEST="$ROOT/bench_common"
rm -rf "$DEST"
cp -R "$SRC" "$DEST"
echo "staged bench_common -> $DEST"
