# Public agentic trading dashboard

A daily, read-only snapshot of the dashboard from
[agentic-trading-research](https://github.com/GeorgeStatho/agentic-trading-research), an LLM-driven options
paper-trading experiment. **View it at <https://georgestatho.github.io/public-agentic-trading-dashboard/>.**

- `gh-pages` is the site: the dashboard built in snapshot mode plus the API responses it reads, replaced by one
  new commit each weekday evening. Nothing in it talks to a server.
- `main` (this branch) is the tooling that makes it.

Figures, positions and status are as of the time in the page's banner. Only the default views are included: other
filters show a load error, and CSV downloads are hidden. All trading is on a paper account.

## How it's made

`publish.sh` runs from cron on the machine that runs the trading stack:

1. builds the trading repo's dashboard with `VITE_SNAPSHOT=1 vite build --base=./`, so every `/api/...` read comes
   from `data/<key>.json` (see `web_dashboard/src/snapshot.ts` there);
2. runs `capture.py` against the local, read-only dashboard (GETs only), saving each route the dashboard reads at its
   default settings, the variants its selectors offer, the latest 25 backtest runs and the 50 recent exposure maps,
   plus `data/manifest.json` (time, what was captured, what failed);
3. force-pushes the result to `gh-pages`, as one commit replacing the last.

The run publishes nothing when no route could be read.

## Set up

1. Clone the trading repo next to this one and run `npm ci` in its `web_dashboard`.
2. Create a deploy key and add its public half to this repo with write access (Settings → Deploy keys), then trust
   GitHub's host key once:
   ```bash
   ssh-keygen -t ed25519 -N '' -C dashboard-snapshot -f ~/.ssh/dashboard_pages
   ssh -T -i ~/.ssh/dashboard_pages -o IdentitiesOnly=yes git@github.com
   ```
3. Run `./publish.sh` once, then turn on Pages: Settings → Pages → Deploy from a branch → `gh-pages`, `/`.
4. Schedule it with `crontab -e` (times are the machine's local time):
   ```
   30 17 * * 1-5  ~/code/public-agentic-trading-dashboard/publish.sh >> ~/dashboard-snapshot.log 2>&1
   ```

| Setting | Default |
| --- | --- |
| `TRADING_REPO` | `~/code/Stock-trading-experiment` |
| `SNAPSHOT_API_BASE` | `http://127.0.0.1:8080` |
| `SNAPSHOT_PAGES_REMOTE` | `git@github.com:GeorgeStatho/public-agentic-trading-dashboard.git` |
| `SNAPSHOT_DEPLOY_KEY` | `~/.ssh/dashboard_pages` |

## Tests

```bash
python3 -m unittest
```

The check that `capture.py` names files the way the dashboard reads them uses the trading repo's
`web_dashboard/src/test/contracts/snapshot-keys.json` (from `TRADING_REPO`) and is skipped without it.
