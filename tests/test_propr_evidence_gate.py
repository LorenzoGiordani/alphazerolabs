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


def test_propr_snapshot_only_reads_account_without_orders(tmp_path, monkeypatch):
    import scripts.propr_paper as propr

    status = tmp_path / "propr_status.json"
    monkeypatch.setattr(propr, "STATUS_PATH", status)
    monkeypatch.setattr(propr, "load", lambda _path: {
        "id": "alpha-port-v1", "status": "champion", "engine": "portfolio"})
    evidence = {"verified": False, "status": "blocked", "reasons": ["checker_missing"]}
    monkeypatch.setattr(propr, "verify_evidence", lambda _spec, _root: evidence.copy())

    class ReadOnlyClient:
        def __init__(self, *, read_only=False):
            assert read_only is True

        def setup(self):
            self.account_id = "paper-1"
            return self.account_id

        def _req(self, method, path, **_kwargs):
            assert (method, path) == ("GET", "/challenge-attempts")
            return {"data": [{
                "accountId": "paper-1", "status": "active", "startedAt": "2026-07-08T00:00:00Z",
                "challenge": {"name": "Free Trial", "slug": "free-trial", "initialBalance": 5000,
                              "phases": [{"profitTargetPercent": 10, "maxDailyLossPercent": 3,
                                          "maxDrawdownPercent": 6}]}}]}

        def get_positions(self):
            return [{"base": "ETH", "positionSide": "long", "notionalValue": "250",
                     "unrealizedPnl": "12"}]

        def get_account(self):
            return {"balance": "5004", "totalUnrealizedPnl": "12", "highWaterMark": "5030"}

        def create_order(self, **_kwargs):
            raise AssertionError("snapshot-only must not create orders")

    monkeypatch.setattr(propr, "ProprClient", ReadOnlyClient)
    propr.main(snapshot_only=True)
    payload = json.loads(status.read_text())
    assert payload["strategy"] == "llm-discretionary-v1"
    assert payload["execution_mode"] == "llm-discretionary"
    assert payload["trading_blocked"] is False
    assert payload["equity"] == 5016.0
    assert payload["positions"][0]["asset"] == "ETH"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_propr_read_only_client_blocks_writes_before_transport(monkeypatch, method):
    from scripts.propr_client import ProprClient, ProprError

    def forbidden_transport(*_args, **_kwargs):
        raise AssertionError("network transport reached")

    monkeypatch.setattr("scripts.propr_client.requests.request", forbidden_transport)
    client = ProprClient("paper-key", read_only=True)
    with pytest.raises(ProprError, match="client read-only"):
        client._req(method, "/accounts/paper-1/orders")
