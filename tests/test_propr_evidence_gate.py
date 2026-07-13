import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_propr_blocks_before_client_or_network(tmp_path, monkeypatch):
    import scripts.propr_paper as propr

    status = tmp_path / "propr_status.json"
    monkeypatch.setattr(propr, "STATUS_PATH", status)
    monkeypatch.setattr(propr, "load",
                        lambda _path: {"id": "alpha-v1", "status": "champion"})
    monkeypatch.setattr(propr, "verify_evidence", lambda _spec, _root: {
        "verified": False, "status": "blocked", "reasons": ["checker_missing"],
        "dsr": None, "maker_run_id": None, "checker_run_id": None})

    def forbidden_client():
        raise AssertionError("ProprClient/network reached before evidence gate")

    monkeypatch.setattr(propr, "ProprClient", forbidden_client)
    with pytest.raises(SystemExit) as exc:
        propr.main()
    assert exc.value.code == 2
    payload = json.loads(status.read_text())
    assert payload["trading_blocked"] is True
    assert payload["trading_block_reason"] == "evidence_not_verified"


def test_propr_portfolio_stays_blocked_even_with_verified_evidence(tmp_path, monkeypatch):
    import scripts.propr_paper as propr

    status = tmp_path / "propr_status.json"
    monkeypatch.setattr(propr, "STATUS_PATH", status)
    monkeypatch.setattr(propr, "load", lambda _path: {
        "id": "alpha-port-v1", "status": "champion", "engine": "portfolio"})
    monkeypatch.setattr(propr, "verify_evidence", lambda _spec, _root: {
        "verified": True, "status": "verified", "reasons": [], "dsr": 0.99,
        "maker_run_id": "maker-1", "checker_run_id": "checker-1"})

    def forbidden_client():
        raise AssertionError("portfolio Propr contract is not verified")

    monkeypatch.setattr(propr, "ProprClient", forbidden_client)
    with pytest.raises(SystemExit) as exc:
        propr.main()
    assert exc.value.code == 2
    payload = json.loads(status.read_text())
    assert payload["trading_block_reason"] == "portfolio_execution_contract_not_verified"
    assert "portfolio_execution_contract_not_verified" in payload["evidence"]["reasons"]
