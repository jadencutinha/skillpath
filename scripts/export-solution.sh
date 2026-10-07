#!/usr/bin/env bash
# Export the TrainingRequests solution from Dataverse and unpack it into ./src as readable source.
# Prereqs: pac CLI (VS Code Power Platform Tools, or `dotnet tool install --global Microsoft.PowerApps.CLI.Tool`)
#          and `pac auth create --environment https://<org>.crm.dynamics.com` run once.
#
# Both the unmanaged and the managed package are exported and unpacked together
# (--packagetype Both). That is what lets pack-solution.sh build a managed zip from source
# for test and production, without going back to the dev environment.
set -euo pipefail

SOLUTION="${SOLUTION:-TrainingRequests}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/out/export"

mkdir -p "$OUT"
echo "Exporting $SOLUTION (unmanaged)..."
pac solution export --name "$SOLUTION" --path "$OUT/$SOLUTION.zip" --overwrite

# The managed zip must sit next to the unmanaged one with a _managed suffix for unpack to find it.
echo "Exporting $SOLUTION (managed)..."
pac solution export --name "$SOLUTION" --path "$OUT/${SOLUTION}_managed.zip" --managed --overwrite

echo "Unpacking into src/ ..."
pac solution unpack --zipfile "$OUT/$SOLUTION.zip" --folder "$ROOT/src" \
  --packagetype Both --processCanvasApps --allowDelete --allowWrite

echo "Done. Review with: git status src/"
