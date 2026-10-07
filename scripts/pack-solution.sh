#!/usr/bin/env bash
# Rebuild a solution zip from ./src (the reverse of export-solution.sh).
#
#   ./scripts/pack-solution.sh             # managed   -> out/pack/TrainingRequests_managed.zip
#   ./scripts/pack-solution.sh Unmanaged   # unmanaged -> out/pack/TrainingRequests.zip
#
# Import MANAGED into test and production: it can't be edited there, and uninstalling it removes
# its components cleanly. Import UNMANAGED only into another development environment.
#   pac solution import --path out/pack/TrainingRequests_managed.zip \
#     --settings-file deploy/settings.test.json
set -euo pipefail

SOLUTION="${SOLUTION:-TrainingRequests}"
TYPE="${1:-Managed}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/out/pack"

case "$TYPE" in
  Managed)   ZIP="$OUT/${SOLUTION}_managed.zip" ;;
  Unmanaged) ZIP="$OUT/$SOLUTION.zip" ;;
  *) echo "Usage: $0 [Managed|Unmanaged]" >&2; exit 2 ;;
esac

if [ ! -f "$ROOT/src/Other/Solution.xml" ]; then
  echo "src/ has no unpacked solution yet. Run scripts/export-solution.sh first." >&2
  exit 1
fi

mkdir -p "$OUT"
pac solution pack --zipfile "$ZIP" --folder "$ROOT/src" --packagetype "$TYPE" --processCanvasApps
echo "Packed: ${ZIP#"$ROOT"/}"
