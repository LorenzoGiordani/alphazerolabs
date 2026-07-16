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
