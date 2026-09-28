#!/usr/bin/env bash
# Rebuild a solution zip from ./src (the reverse of export-solution.sh), e.g. to import into another environment:
#   ./scripts/pack-solution.sh && pac solution import --path out/TrainingRequests_packed.zip
set -euo pipefail

SOLUTION="${SOLUTION:-TrainingRequests}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$ROOT/out"
pac solution pack --zipfile "$ROOT/out/${SOLUTION}_packed.zip" --folder "$ROOT/src" --processCanvasApps
echo "Packed: out/${SOLUTION}_packed.zip"
