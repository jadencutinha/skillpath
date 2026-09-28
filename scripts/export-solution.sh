#!/usr/bin/env bash
# Export the TrainingRequests solution from Dataverse and unpack it into ./src as readable source.
# Prereqs: pac CLI (VS Code Power Platform Tools, or `dotnet tool install --global Microsoft.PowerApps.CLI.Tool`)
#          and `pac auth create --environment https://<org>.crm.dynamics.com` run once.
set -euo pipefail

SOLUTION="${SOLUTION:-TrainingRequests}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZIP="$ROOT/out/$SOLUTION.zip"

mkdir -p "$ROOT/out"
echo "Exporting $SOLUTION (unmanaged)..."
pac solution export --name "$SOLUTION" --path "$ZIP" --overwrite

echo "Unpacking into src/ ..."
pac solution unpack --zipfile "$ZIP" --folder "$ROOT/src" --processCanvasApps --allowDelete --allowWrite

echo "Done. Review with: git status src/"
