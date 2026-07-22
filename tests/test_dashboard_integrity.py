import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_dashboard_keeps_paper_status_separate_from_evidence(tmp_path, monkeypatch):
    import backtest.evidence as evidence
    import backtest.lifecycle as lifecycle
    import scripts.dashboard as dashboard

    spec = {"id": "xsmom-multihorizon-v1", "status": "champion", "risk": {}}
    monkeypatch.setattr(lifecycle, "all_specs", lambda: [(tmp_path / "s.yaml", spec)])
    monkeypatch.setattr(lifecycle, "paper_symbols", lambda _spec: "BTC,ETH,SOL")
    monkeypatch.setattr(lifecycle, "paper_stats", lambda _sid: {})
    monkeypatch.setattr(evidence, "verify_evidence", lambda _spec, _root: {
        "verified": False, "status": "blocked", "reasons": ["checker_missing"]})
    row = dashboard.build_strategies({})[0]
    assert row["paper_status"] == "champion"
    assert row["evidence"]["verified"] is False
    assert row["evidence_ready"] is False


def test_dashboard_health_missing_is_fail_closed(tmp_path):
    import scripts.dashboard as dashboard

    health = dashboard.load_runtime_health(tmp_path)
    assert health["status"] == "unknown"
    assert health["publish_allowed"] is False
    assert health["validation_reasons"] == ["health_missing"]


def test_open_dashboard_rechecks_health_freshness():
    template = (Path(__file__).resolve().parent.parent / "dashboard/template.html").read_text()
    assert "setInterval(renderHealth, 60000)" in template
    assert "host.hidden=status==='healthy'||status==='degraded'" in template
    assert "#health-banner[hidden]{ display:none; }" in template


def test_dashboard_uses_sp500_benchmark(monkeypatch):
    import pandas as pd
    import pipeline.live as live
    import scripts.dashboard as dashboard

    candles = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-01T15:00Z", "2026-01-02T15:00Z",
                              "2026-01-03T15:00Z"]),
        "close": [99.0, 100.0, 105.0],
    })
    calls = []

    def fake_fetch(symbol, lookback_h):
        calls.append((symbol, lookback_h))
        return {"candles": candles}

    monkeypatch.setattr(live, "fetch_live_cached", fake_fetch)
    result = dashboard.benchmark_sp500([
        {"equity_curve": [["2026-01-02 12:00", 10_000.0]]},
    ])

    assert calls == [("xyz_SP500", 1200)]
    assert result == {
        "symbol": "SP500", "start": "2026-01-02 12:00", "pct": 6.06,
        "px_start": 99.0, "px_now": 105.0,
    }
    template = (Path(__file__).resolve().parent.parent / "dashboard/template.html").read_text()
    assert "rendimento assoluto" in template
    assert "const benchmarkUsd=base*b.pct/100" in template
    assert "const diffUsd=wr-benchmarkUsd" in template
    assert "signedUsd(benchmarkUsd)" in template
    assert "signedUsd(diffUsd)" in template
    assert "lo stesso capitale sull\\'S&amp;P 500" in template
    assert "comprare e tenere Bitcoin" not in template
