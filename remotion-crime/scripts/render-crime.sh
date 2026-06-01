#!/usr/bin/env bash
# Render a single crime reel from an external case JSON.
#
# Usage:
#   render-crime.sh --case CASE_JSON --assets ASSETS_DIR --out OUT_MP4
#
# The ASSETS_DIR must contain all mp3 + images referenced by the case JSON.
# Expected layout (matches Case schema):
#   ASSETS_DIR/
#     hook.mp3
#     setup.mp3
#     event-1.mp3 … event-N.mp3
#     twist.mp3
#     aftermath.mp3
#     cta.mp3
#     images/*.jpg
#
# The script copies ASSETS_DIR into public/crime/{case.id}/ before rendering.
# If the case.id already exists in public/crime/, its contents are replaced.

set -euo pipefail

CASE_JSON=""
ASSETS_DIR=""
OUT_MP4=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --case)   CASE_JSON="$2"; shift 2 ;;
    --assets) ASSETS_DIR="$2"; shift 2 ;;
    --out)    OUT_MP4="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

for var in CASE_JSON ASSETS_DIR OUT_MP4; do
  if [[ -z "${!var}" ]]; then
    echo "Missing --${var,,} (try --help)" >&2
    exit 1
  fi
done

if [[ ! -f "$CASE_JSON" ]]; then
  echo "Case JSON not found: $CASE_JSON" >&2
  exit 1
fi
if [[ ! -d "$ASSETS_DIR" ]]; then
  echo "Assets dir not found: $ASSETS_DIR" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

CASE_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$CASE_JSON")"
if [[ -z "$CASE_ID" ]]; then
  echo "case.id missing in $CASE_JSON" >&2
  exit 1
fi

DEST="$PROJECT_DIR/public/crime/$CASE_ID"
mkdir -p "$DEST"
# rsync keeps existing music/bgm untouched; we only sync the per-case assets
rsync -a --delete "$ASSETS_DIR/" "$DEST/"

# Load case JSON into a single-line JSON string for --props
PROPS_JSON="$(python3 -c '
import json, sys
case = json.load(open(sys.argv[1]))
print(json.dumps({"c": case}, ensure_ascii=False))
' "$CASE_JSON")"

mkdir -p "$(dirname "$OUT_MP4")"

cd "$PROJECT_DIR"
./node_modules/.bin/remotion render \
  src/index.ts Crime "$OUT_MP4" \
  --props="$PROPS_JSON" \
  --log=error

echo "✓ Rendered $OUT_MP4"
