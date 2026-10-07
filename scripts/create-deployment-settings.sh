#!/usr/bin/env bash
# Generate a deployment settings file listing every environment variable and connection
# reference the solution contains, with empty values to fill in for one target environment.
#
#   ./scripts/create-deployment-settings.sh test    # -> deploy/settings.test.json
#
# Run it again after adding an environment variable or a connector to the solution, and
# merge the new entries into the existing file. See deploy/README.md.
set -euo pipefail

TARGET="${1:?Usage: $0 <environment name, e.g. test or prod>}"
SOLUTION="${SOLUTION:-TrainingRequests}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZIP="$ROOT/out/pack/${SOLUTION}_managed.zip"
SETTINGS="$ROOT/deploy/settings.$TARGET.json"

if [ ! -f "$ZIP" ]; then
  "$ROOT/scripts/pack-solution.sh" Managed
fi
if [ -e "$SETTINGS" ]; then
  # Never clobber a filled-in file: write the fresh template next to it instead.
  SETTINGS="$ROOT/deploy/settings.$TARGET.new.json"
  echo "deploy/settings.$TARGET.json exists; writing the fresh template to ${SETTINGS#"$ROOT"/}"
fi

pac solution create-settings --solution-zip "$ZIP" --settings-file "$SETTINGS"
echo "Wrote ${SETTINGS#"$ROOT"/}. Fill in each Value and ConnectionId."
