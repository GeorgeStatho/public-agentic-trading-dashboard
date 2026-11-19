"""capture.py saves the read-only API as static files that the dashboard's snapshot build reads back.

Run with `python3 -m unittest`. The file-name check reads the dashboard's own examples from the trading repo
(TRADING_REPO, default ~/code/Stock-trading-experiment) and is skipped without it."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("capture.py")
TRADING_REPO = Path(os.getenv("TRADING_REPO", Path.home() / "code" / "Stock-trading-experiment"))
KEY_EXAMPLES = TRADING_REPO / "web_dashboard" / "src" / "test" / "contracts" / "snapshot-keys.json"


def _load():
    spec = importlib.util.spec_from_file_location("dashboard_snapshot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeApi:
    """Answers every listed route; backtests and articles list two ids each."""

    def __init__(self, failing: set[str] = frozenset()):
        self.requested: list[str] = []
        self.failing = failing

    def __call__(self, url: str):
        self.requested.append(url)
        if url in self.failing:
            raise OSError("boom")
        if url == "/api/backtests?limit=100":
            return {"runs": [{"id": 140}, {"id": 138}]}
        if url == "/api/exposure-map/articles?limit=50":
            return {"articles": [{"id": 13449}, {"id": 12748}]}
        return {"url": url}


class DashboardSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.module = _load()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name) / "data"

    @unittest.skipUnless(KEY_EXAMPLES.exists(), "needs the trading repo's snapshot-keys.json (set TRADING_REPO)")
    def test_keys_match_the_examples_the_dashboard_also_checks(self):
        for url, key in json.loads(KEY_EXAMPLES.read_text(encoding="utf-8")).items():
            self.assertEqual(key, self.module.snapshot_key(url), url)

    def test_saves_each_route_under_its_key_with_a_manifest(self):
        manifest = self.module.snapshot(FakeApi(), self.out)
        self.assertEqual({"url": "/api/dashboard-kpis"}, json.loads((self.out / "dashboard-kpis.json").read_text()))
        self.assertIn("/api/decision-attribution?days=90&horizon=10", manifest["captured"])
        self.assertEqual(manifest, json.loads((self.out / "manifest.json").read_text()))
        self.assertTrue(manifest["captured_at"])

    def test_follows_backtest_runs_and_exposure_maps(self):
        api = FakeApi()
        self.module.snapshot(api, self.out)
        for url in ("/api/backtests/140", "/api/backtests/138", "/api/exposure-map/13449", "/api/exposure-map/12748"):
            self.assertIn(url, api.requested)
        self.assertTrue((self.out / "backtests_140.json").exists())

    def test_only_the_latest_backtest_runs_are_kept(self):
        api = FakeApi()
        self.module.snapshot(api, self.out, backtest_runs=1)
        self.assertIn("/api/backtests/140", api.requested)
        self.assertNotIn("/api/backtests/138", api.requested)

    def test_a_failed_route_is_recorded_and_the_rest_still_saved(self):
        manifest = self.module.snapshot(FakeApi(failing={"/api/portfolio-history"}), self.out)
        self.assertIn("/api/portfolio-history", manifest["failed"])
        self.assertFalse((self.out / "portfolio-history.json").exists())
        self.assertTrue((self.out / "dashboard-kpis.json").exists())

    def test_two_routes_with_one_key_are_refused(self):
        with patch.object(self.module, "ROUTES", ("/api/a.b", "/api/a_b")), self.assertRaises(ValueError):
            self.module.snapshot(FakeApi(), self.out)

    def test_http_fetch_only_gets(self):
        sent = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b'{"ok": true}'

        def fake_urlopen(request, timeout):
            sent.append(request)
            return Response()

        with patch.object(self.module, "urlopen", fake_urlopen), patch.object(self.module.time, "sleep"):
            fetch = self.module.http_fetch("https://dash.example.com/")
            self.assertEqual({"ok": True}, fetch("/api/dashboard-kpis"))
        request = sent[0]
        self.assertEqual("GET", request.get_method())
        self.assertEqual("https://dash.example.com/api/dashboard-kpis", request.full_url)


if __name__ == "__main__":
    unittest.main()
