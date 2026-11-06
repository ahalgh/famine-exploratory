#!/usr/bin/env bash
# Build the public site for GitHub Pages and, with --deploy, push it to the gh-pages branch.
#
#   scripts/publish_site.sh            build web/dist-public only (inspect it before deploying)
#   scripts/publish_site.sh --deploy   build, then commit the build to gh-pages and push it
#
# The public build differs from local development in two ways:
#   - it is served from /famine-exploratory/ (GitHub Pages project site), and
#   - ACLED conflict series are removed from history.json, as ACLED's terms restrict redistribution.
# Run scripts/export_map_data.py first so web/public/data is current.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/web/dist-public"
BASE_PATH="${BASE_PATH:-/famine-exploratory/}"

cd "$ROOT/web"
BASE_PATH="$BASE_PATH" VITE_PUBLIC=1 npm run build -- --outDir "$OUT" --emptyOutDir

python3 - "$OUT/data/history.json" <<'PY'
import json, sys
p = sys.argv[1]
h = json.load(open(p))
h["conflict"] = {}
h["public"] = True
json.dump(h, open(p, "w"), separators=(",", ":"))
print(f"stripped ACLED conflict series from {p}")
PY
touch "$OUT/.nojekyll"   # serve files as-is (no Jekyll processing)
echo "built $OUT ($(du -sh "$OUT" | cut -f1))"

[[ "${1:-}" == "--deploy" ]] || exit 0

cd "$ROOT"
SRC_SHA="$(git rev-parse --short HEAD)"
TMP="$(mktemp -d)"
git fetch origin gh-pages 2>/dev/null || true
if git show-ref --verify --quiet refs/remotes/origin/gh-pages; then
  git worktree add -B gh-pages "$TMP" origin/gh-pages
else
  # first deploy: start gh-pages from an empty root commit, unrelated to the source branches
  ROOT_COMMIT="$(git commit-tree "$(git hash-object -t tree /dev/null)" -m "gh-pages root")"
  git branch -f gh-pages "$ROOT_COMMIT"
  git worktree add "$TMP" gh-pages
fi
rsync -a --delete --exclude .git --exclude boundary-vis "$OUT/" "$TMP/"  # boundary-vis/ is published separately
cd "$TMP"
git add -A
if git diff --cached --quiet; then
  echo "no changes to deploy"
else
  git commit -q -m "Deploy site from $SRC_SHA"
  git push origin gh-pages
fi
cd "$ROOT"
git worktree remove --force "$TMP"
echo "deployed: https://ahalgh.github.io${BASE_PATH}"
