#!/usr/bin/env bash
# Build boundary-vis and publish it to gh-pages/boundary-vis/ (the main site at the root is untouched).
#
#   scripts/publish_boundary_vis.sh            build boundary-vis/dist-public only
#   scripts/publish_boundary_vis.sh --deploy   build, then commit it under boundary-vis/ on gh-pages and push
#
# Run scripts/export_boundaries.py first so boundary-vis/public/data is current.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/boundary-vis/dist-public"
SUB="boundary-vis"

cd "$ROOT/boundary-vis"
BASE_PATH="/famine-exploratory/$SUB/" npm run build -- --outDir "$OUT" --emptyOutDir
echo "built $OUT ($(du -sh "$OUT" | cut -f1))"
[[ "${1:-}" == "--deploy" ]] || exit 0

cd "$ROOT"
SRC_SHA="$(git rev-parse --short HEAD)"
TMP="$(mktemp -d)"
git fetch origin gh-pages
git worktree add -B gh-pages "$TMP" origin/gh-pages
mkdir -p "$TMP/$SUB"
rsync -a --delete "$OUT/" "$TMP/$SUB/"
cd "$TMP"
git add -A "$SUB"
if git diff --cached --quiet; then
  echo "no changes to deploy"
else
  git commit -q -m "Deploy boundary-vis from $SRC_SHA"
  git push origin gh-pages
fi
cd "$ROOT"
git worktree remove --force "$TMP"
echo "deployed: https://ahalgh.github.io/famine-exploratory/$SUB/"
