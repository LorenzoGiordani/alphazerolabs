import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import fetch_coinalyze as fc


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


def _snapshot(path, *, asof=NOW, symbols=("BTC", "ETH")):
    path.mkdir()
    for symbol in symbols:
        (path / f"{symbol}.parquet").write_bytes(b"present")
    (path / "_meta.json").write_text(json.dumps({
        "asof": asof.isoformat(), "symbols": list(symbols), "source_url": fc.BASE, "months": 7,
    }))


def test_historical_snapshot_fresh_requires_age_coverage_and_files(tmp_path):
    out = tmp_path / "coinalyze"; _snapshot(out)
    assert fc.historical_snapshot_fresh(out, ["BTC", "ETH"], 20, now=NOW)
    assert not fc.historical_snapshot_fresh(out, ["BTC"], 20, months=8, now=NOW)
    assert not fc.historical_snapshot_fresh(out, ["BTC", "SOL"], 20, now=NOW)
    (out / "ETH.parquet").unlink()
    assert not fc.historical_snapshot_fresh(out, ["BTC", "ETH"], 20, now=NOW)


def test_historical_snapshot_rejects_stale_or_future_meta(tmp_path):
    stale = tmp_path / "stale"; _snapshot(stale, asof=NOW - timedelta(hours=21))
    future = tmp_path / "future"; _snapshot(future, asof=NOW + timedelta(minutes=6))
    assert not fc.historical_snapshot_fresh(stale, ["BTC"], 20, now=NOW)
    assert not fc.historical_snapshot_fresh(future, ["BTC"], 20, now=NOW)


def test_cli_fresh_gate_skips_api_key_and_network(tmp_path, monkeypatch):
    out = tmp_path / "coinalyze"; _snapshot(out)
    monkeypatch.setattr(fc, "OUT_DIR", out)
    monkeypatch.setattr(fc, "api_key", lambda: (_ for _ in ()).throw(AssertionError("api called")))
    monkeypatch.setattr(fc, "datetime", type("FixedDateTime", (datetime,), {
        "now": classmethod(lambda cls, tz=None: NOW),
    }))
    monkeypatch.setattr(sys, "argv", ["fetch_coinalyze.py", "--symbols", "BTC,ETH",
                                      "--if-fresh-hours", "20"])
    fc.main()


def test_daily_history_runs_only_in_dedicated_collector_workflow():
    root = Path(__file__).resolve().parent.parent
    paper = (root / ".github/workflows/paper-run.yml").read_text()
    collector = (root / ".github/workflows/coinalyze-1h.yml").read_text()
    assert "fetch_coinalyze.py" not in paper
    assert "coinalyze_daily" not in paper
    assert "fetch_coinalyze.py" in collector
    assert "--if-fresh-hours 20" in collector
    assert "git add data/coinalyze_1h/" in collector
    assert 'steps.coinalyze_daily.outcome }}" = "success"' in collector
    assert "git add data/coinalyze/" in collector
