#!/usr/bin/env bash
# Publish a static snapshot of the dashboard to a public site repo's gh-pages branch, which GitHub Pages serves.
# The site repo holds only this output; the code repo's README links to its Pages URL.
# Run daily from cron on the machine that runs the trading stack:
#   30 17 * * 1-5  /path/to/public-agentic-trading-dashboard/publish.sh >> ~/dashboard-snapshot.log 2>&1
# Reads the local read-only dashboard; pushes only the built site, as one commit that replaces the last.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The trading repo checkout whose dashboard is built (its web_dashboard needs `npm ci` once).
TRADING_REPO="${TRADING_REPO:-$HOME/code/Stock-trading-experiment}"
BASE="${SNAPSHOT_API_BASE:-http://127.0.0.1:8080}"
REMOTE="${SNAPSHOT_PAGES_REMOTE:-git@github.com:GeorgeStatho/public-agentic-trading-dashboard.git}"
# A deploy key with write access to the site repo only: if it leaked, only the snapshot site could change.
KEY="${SNAPSHOT_DEPLOY_KEY:-$HOME/.ssh/dashboard_pages}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$TRADING_REPO/web_dashboard"
VITE_SNAPSHOT=1 npx vite build --base=./ --outDir "$WORK/site" --emptyOutDir --logLevel warn
# Vite copies all of public/, including untracked local output files (portfolio_history.json and the like).
rm -f "$WORK/site/"*.json
python3 "$HERE/capture.py" --base "$BASE" --out "$WORK/site/data"
touch "$WORK/site/.nojekyll"  # serve files as they are; Jekyll would skip names starting with _

cd "$WORK/site"
git init -q -b gh-pages
git add -A
git -c user.name="dashboard-snapshot" -c user.email="dashboard-snapshot@users.noreply.github.com" \
  commit -q -m "Dashboard snapshot $(date -u +%Y-%m-%dT%H:%MZ)"
if [[ "$REMOTE" == git@* ]]; then
  export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes"
fi
git push -q --force "$REMOTE" gh-pages
echo "Published $(git rev-parse --short HEAD) to $REMOTE gh-pages."
