#!/usr/bin/env python3
"""Save the dashboard's read-only API as static JSON files for the snapshot build on GitHub Pages.

Standard library only, GETs only. `publish.sh` runs it against the local dashboard. The dashboard's snapshot build
(web_dashboard/src/snapshot.ts in the trading repo) reads `<out>/<key>.json`, with the same key rule as
`snapshot_key`.

    python capture.py --base http://127.0.0.1:8080 --out /tmp/site/data
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

WINDOWS = ("0", "30", "90", "180", "365")
EXTRACTION_WINDOWS = ("1", "7", "30", "90")
SCOPES = ("company", "sector", "industry", "macro")

# Every request the dashboard makes at its default settings, plus the variants its selectors offer.
ROUTES: tuple[str, ...] = (
    "/api/dashboard-kpis",
    "/api/script-status",
    "/api/portfolio-history",
    "/api/open-positions",
    "/api/executed-trades",
    "/api/why-bot-traded",
    "/api/risk-controls",
    "/api/company-decisions",
    "/api/decision-autopsies?limit=100",
    "/api/demo-mode",
    "/api/forward-evaluation",
    "/api/v2-status",
    "/api/exit-attribution",
    "/api/execution-quality?days=30",
    "/api/llm-usage?days=30",
    "/api/macro-calendar?days=7",
    "/api/decision-attribution?days=90&horizon=5",
    "/api/decision-attribution?days=90&horizon=10",
    "/api/decision-expectancy?basis=marked&group_by=confidence&within_days=90&min_samples=5&decision=all&confidence=all",
    "/api/news-lag",
    *(f"/api/news-lag?days={days}" for days in WINDOWS),
    *(f"/api/follower-accounts?days={days}" for days in WINDOWS),
    *(f"/api/news-extraction?days={days}" for days in EXTRACTION_WINDOWS),
    "/api/opportunist-company-news",
    *(f"/api/opportunist-company-news?page=1&page_size=5&view={scope}" for scope in SCOPES),
    "/api/backtests?limit=100",
    "/api/exposure-map/articles?limit=50",
)
BACKTEST_LIST = "/api/backtests?limit=100"
ARTICLE_LIST = "/api/exposure-map/articles?limit=50"
REQUEST_GAP_SECONDS = 0.25  # under nginx's 10 requests a second per visitor
# Scraped article text belongs to its publishers: the public site never carries it, whatever the API returns.
ARTICLE_TEXT_KEYS = frozenset({"body", "raw_json"})


def without_article_text(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: without_article_text(value) for key, value in node.items() if key not in ARTICLE_TEXT_KEYS}
    if isinstance(node, list):
        return [without_article_text(value) for value in node]
    return node


def snapshot_key(url: str) -> str:
    """`/api/x?b=2&a=1&ts=…` → `x_a_1_b_2`: path and sorted, decoded parameters without the cache-buster."""
    parts = urlsplit(url)
    path = parts.path.removeprefix("/api/")
    pairs = sorted((key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "ts")
    text = path + ("?" + "&".join(f"{key}={value}" for key, value in pairs) if pairs else "")
    return re.sub(r"[^A-Za-z0-9-]", "_", text)


def _ids(payload: Any, field: str) -> list[int]:
    rows = payload.get(field) if isinstance(payload, dict) else None
    return [row["id"] for row in rows or [] if isinstance(row, dict) and isinstance(row.get("id"), int)]


def snapshot(fetch: Callable[[str], Any], out_dir: Path, *, backtest_runs: int = 25) -> dict[str, Any]:
    """GET every route (and the runs and articles their lists name), save each under its key, return the manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"captured_at": datetime.now(UTC).isoformat(), "captured": [], "failed": {}}
    keys: dict[str, str] = {}
    pending = list(ROUTES)
    while pending:
        url = pending.pop(0)
        key = snapshot_key(url)
        if keys.setdefault(key, url) != url:
            raise ValueError(f"{url} and {keys[key]} would share the file {key}.json")
        try:
            payload = fetch(url)
        except Exception as exc:  # noqa: BLE001 - one broken route must not cost the whole snapshot
            manifest["failed"][url] = str(exc) or type(exc).__name__
            continue
        (out_dir / f"{key}.json").write_text(json.dumps(without_article_text(payload)), encoding="utf-8")
        manifest["captured"].append(url)
        if url == BACKTEST_LIST:
            pending += [f"/api/backtests/{run_id}" for run_id in _ids(payload, "runs")[:backtest_runs]]
        elif url == ARTICLE_LIST:
            pending += [f"/api/exposure-map/{article_id}" for article_id in _ids(payload, "articles")]
    (out_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def http_fetch(base: str, timeout: float = 60.0) -> Callable[[str], Any]:
    headers = {"User-Agent": "dashboard-snapshot/1", "Accept": "application/json"}

    def fetch(url: str) -> Any:
        time.sleep(REQUEST_GAP_SECONDS)
        with urlopen(Request(base.rstrip("/") + url, headers=headers, method="GET"), timeout=timeout) as response:
            return json.loads(response.read())

    return fetch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="Dashboard origin, e.g. http://127.0.0.1:8080")
    parser.add_argument("--out", type=Path, required=True, help="Directory for the JSON files")
    parser.add_argument("--backtest-runs", type=int, default=25, help="Latest backtest runs to save in full")
    args = parser.parse_args(argv)
    manifest = snapshot(http_fetch(args.base), args.out, backtest_runs=args.backtest_runs)
    print(f"Saved {len(manifest['captured'])} routes; {len(manifest['failed'])} failed.")
    for url, error in manifest["failed"].items():
        print(f"  failed {url}: {error}", file=sys.stderr)
    # Nothing saved means the dashboard is down: fail rather than publish an empty site.
    return 0 if manifest["captured"] else 1


if __name__ == "__main__":
    sys.exit(main())
