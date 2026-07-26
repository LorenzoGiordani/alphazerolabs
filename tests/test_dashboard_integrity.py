import sys
from datetime import datetime, timedelta, timezone
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


def test_public_status_is_stopped_and_bound_to_runtime_evidence():
    import scripts.dashboard as dashboard

    older = datetime(2026, 7, 24, 23, tzinfo=timezone.utc)
    newer = older + timedelta(minutes=4)
    health = {
        "status": "healthy",
        "publish_allowed": True,
        "run_id": "42-1",
        "commit": "abc",
        "generated_at": (newer + timedelta(minutes=1)).isoformat(),
        "attestation_sha256": "a" * 64,
        "validation_reasons": [],
        "coverage": [
            {"generated_at": older.isoformat()},
            {"generated_at": newer.isoformat()},
        ],
    }
    strategies = [
        {"id": "alpha-v1", "status": "champion",
         "evidence": {"verified": False, "status": "blocked"}},
        {"id": "agents-v1", "status": "live"},
        {"id": "old-v1", "status": "retired",
         "evidence": {"verified": False, "status": "blocked"}},
    ]

    status = dashboard.build_public_status(health, strategies)

    assert status["state"] == "stopped"
    assert status["source"]["last_evidence_at"] == newer.isoformat()
    assert status["summary"] == {
        "active": 0, "stopped": 2, "archived": 1, "experiments": 1,
    }
    assert {row["id"]: row["state"] for row in status["strategies"]} == {
        "alpha-v1": "stopped", "agents-v1": "stopped", "old-v1": "archived",
    }
    assert len(status["attestation_sha256"]) == 64


def test_public_status_does_not_use_health_build_time_as_evidence():
    import scripts.dashboard as dashboard

    status = dashboard.build_public_status({
        "status": "healthy",
        "publish_allowed": True,
        "run_id": "42-1",
        "commit": "abc",
        "generated_at": datetime(2026, 7, 25, tzinfo=timezone.utc).isoformat(),
        "validation_reasons": [],
        "coverage": [],
    }, [])

    assert status["state"] == "stopped"
    assert status["source"]["last_evidence_at"] is None


def test_public_navigation_has_three_clear_destinations():
    import scripts.dashboard as dashboard

    assert [name for name, _pages in dashboard.NAV_GROUPS] == [
        "Stato", "Strategie", "Metodo",
    ]
    nav = dashboard._nav_inner("index.html")
    assert "Propr" not in nav
    assert "Evoluzione" not in nav


def test_open_dashboard_rechecks_health_freshness():
    template = (Path(__file__).resolve().parent.parent / "dashboard/template.html").read_text()
    assert "setInterval(renderHealth, 60000)" in template
    assert "host.hidden=publicState==='active'&&(status==='healthy'||status==='degraded')" in template
    assert "#health-banner[hidden]{ display:none; }" in template
    assert "Sistema non operativo. I dati visibili sono uno snapshot storico" in template
    assert "Book e rischio sono verificati ogni ora" not in template
    assert "a ogni run il sistema promuove" not in template
    assert "strategie attive" not in template


def test_stopped_public_status_disables_live_market_requests():
    root = Path(__file__).resolve().parent.parent
    template = (root / "dashboard/template.html").read_text()
    skill = (root / "dashboard/SKILL.md").read_text()

    assert "if((DATA.public_status||{}).state==='active') startLive();" in template
    assert "if(ticker&&!publicActive) ticker.hidden=true;" in template
    assert "if(ticker&&publicActive){" in template
    assert "Read `status.json` before interpreting any other file." in skill
    assert "live track record" not in skill
    assert "autonomous trading-research platform" not in skill


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
