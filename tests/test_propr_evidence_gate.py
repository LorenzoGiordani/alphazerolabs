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
            self.active_attempt = {
                "accountId": "paper-1", "status": "active", "startedAt": "2026-07-08T00:00:00Z",
                "challenge": {"name": "Free Trial", "slug": "free-trial", "initialBalance": 5000,
                              "phases": [{"profitTargetPercent": 10, "maxDailyLossPercent": 3,
                                          "maxDrawdownPercent": 6}]}}

        def setup(self, *, expected_account_id=None, expected_challenge_slug=None):
            assert expected_account_id is None
            assert expected_challenge_slug is None
            self.account_id = "paper-1"
            return self.account_id

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
    assert payload["paper_only"] is True
    assert payload["official_candidate"] is False
    assert payload["equity"] == 5016.0
    assert payload["positions"][0]["asset"] == "ETH"


def test_propr_manage_kill_switch_blocks_before_client(monkeypatch):
    import scripts.propr_paper as propr

    monkeypatch.delenv("PROPR_AUTOMANAGE_ENABLED", raising=False)
    monkeypatch.setattr(propr, "load", lambda _path: {"id": "alpha-port-v1", "status": "champion"})
    monkeypatch.setattr(propr, "verify_evidence", lambda _spec, _root: {
        "verified": False, "status": "blocked", "reasons": ["checker_missing"]})
    monkeypatch.setattr(propr, "ProprClient",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("client reached while kill switch disabled")))

    propr.main(manage_paper=True)


def test_propr_manage_requires_account_pin_before_client(monkeypatch):
    import scripts.propr_paper as propr

    monkeypatch.setenv("PROPR_AUTOMANAGE_ENABLED", "true")
    monkeypatch.delenv("PROPR_EXPECTED_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(propr, "load", lambda _path: {"id": "alpha-port-v1", "status": "champion"})
    monkeypatch.setattr(propr, "verify_evidence", lambda _spec, _root: {
        "verified": False, "status": "blocked", "reasons": ["checker_missing"]})
    monkeypatch.setattr(propr, "ProprClient",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("client reached without account pin")))

    with pytest.raises(SystemExit, match="PROPR_EXPECTED_ACCOUNT_ID"):
        propr.main(manage_paper=True)


def test_fresh_management_state_discards_legacy_targets():
    from datetime import datetime, timezone
    import scripts.propr_paper as propr

    state = propr._fresh_management_state(5028.23, datetime(2026, 7, 17, tzinfo=timezone.utc))
    assert state["management_mode"] == propr.AUTOMANAGE_VERSION
    assert state["day_start_equity"] == 5028.23
    assert "last_target" not in state
    assert "tranches" not in state


def test_protection_summary_counts_only_native_reduce_only_closes():
    import scripts.propr_paper as propr

    positions = [
        {"positionId": "p1", "positionSide": "long"},
        {"positionId": "p2", "positionSide": "short"},
    ]
    orders = [
        {"positionId": "p1", "type": "stop_market", "side": "sell", "positionSide": "long",
         "reduceOnly": True, "closePosition": True},
        {"positionId": "p2", "type": "stop_market", "side": "sell", "positionSide": "long",
         "reduceOnly": True, "closePosition": True},
    ]
    summary = propr._protection_summary(positions, orders)
    assert summary["protected_positions"] == 1
    assert summary["open_positions"] == 2
    assert summary["fully_protected"] is False


def test_manage_rejects_partial_order_action():
    from scripts.propr_client import ProprError
    import scripts.propr_paper as propr

    with pytest.raises(ProprError, match="azione Propr parziale"):
        propr._raise_on_order_errors([
            {"asset": "BTC", "action": "adjust"},
            {"asset": "ETH", "action": "error", "error": "rejected"},
        ])


def test_rebalance_order_cap_is_checked_before_first_write():
    from scripts.propr_client import ProprError
    import scripts.propr_paper as propr

    class NoWriteClient:
        def create_order(self, **_kwargs):
            raise AssertionError("write reached before order-cap validation")

    positions = [
        {"base": f"A{i:02}", "positionSide": "long", "notionalValue": "10"}
        for i in range(propr.MAX_ORDERS_PER_ACTION + 1)
    ]
    prices = {p["base"]: 1.0 for p in positions}
    with pytest.raises(ProprError, match="ordini > cap"):
        propr.rebalance(NoWriteClient(), {}, prices, positions)


def test_rebalance_missing_price_fails_preflight_before_first_write():
    from scripts.propr_client import ProprError
    import scripts.propr_paper as propr

    class NoWriteClient:
        def create_order(self, **_kwargs):
            raise AssertionError("write reached before price preflight")

    position = {"base": "BTC", "positionSide": "long", "notionalValue": "250"}
    with pytest.raises(ProprError, match="prezzo mancante"):
        propr.rebalance(NoWriteClient(), {}, {}, [position])


def test_first_manage_run_replaces_legacy_state_before_rebalance(tmp_path, monkeypatch):
    import pandas as pd
    import scripts.propr_paper as propr

    state = tmp_path / "propr_state.json"
    status = tmp_path / "propr_status.json"
    state.write_text(json.dumps({
        "last_rebalance_ts": "2026-07-12T23:20:36+00:00",
        "last_target": {"OLD": 999}, "tranches": {"0": {"OLD": 999}},
    }))
    monkeypatch.setattr(propr, "STATE_PATH", state)
    monkeypatch.setattr(propr, "STATUS_PATH", status)
    monkeypatch.setattr(propr, "log_event", lambda _event: None)
    monkeypatch.setattr(propr, "_set_leverage", lambda *_args: None)
    monkeypatch.setattr(propr, "trailing_returns",
                        lambda *_args: ({"BTC": 0.1, "ETH": -0.1}, {"BTC": 100.0, "ETH": 10.0}))
    monkeypatch.setattr(propr, "xs_momentum_weights", lambda *_args, **_kwargs:
                        pd.Series({"BTC": 0.15, "ETH": -0.15}))
    captured = {}
    monkeypatch.setattr(propr, "rebalance",
                        lambda _client, target, _px, _positions: captured.update(target=target) or [])
    monkeypatch.setattr(propr, "load", lambda _path: {
        "id": "alpha-port-v1", "status": "champion", "engine": "portfolio",
        "paper_symbols": "BTC,ETH", "portfolio": {
            "lookbacks_h": [96, 168], "rebalance_h": 168,
            "long_q": 0.66, "short_q": 0.33, "gross": 1.0, "dollar_neutral": True,
        }, "risk": {"max_leverage": 2},
    })
    monkeypatch.setattr(propr, "verify_evidence", lambda _spec, _root: {
        "verified": False, "status": "blocked", "reasons": ["checker_missing"]})
    monkeypatch.setenv("PROPR_AUTOMANAGE_ENABLED", "true")
    monkeypatch.setenv("PROPR_EXPECTED_ACCOUNT_ID", "paper-1")

    class PaperClient:
        def __init__(self):
            self.active_attempt = {
                "accountId": "paper-1", "status": "active", "startedAt": "2026-07-08T00:00:00Z",
                "challenge": {"name": "Free Trial", "slug": "free-trial", "initialBalance": 5000,
                              "phases": [{"profitTargetPercent": 10, "maxDailyLossPercent": 3,
                                          "maxDrawdownPercent": 6}]}}

        def setup(self, **kwargs):
            assert kwargs == {"expected_account_id": "paper-1", "expected_challenge_slug": "free-trial"}
            self.account_id = "paper-1"
            return self.account_id

        def get_account(self):
            return {"balance": "5000", "totalUnrealizedPnl": "0", "highWaterMark": "5000"}

        def get_positions(self):
            return []

    monkeypatch.setattr(propr, "ProprClient", PaperClient)
    propr.main(manage_paper=True)

    saved = json.loads(state.read_text())
    assert saved["management_mode"] == propr.AUTOMANAGE_VERSION
    assert "OLD" not in json.dumps(saved)
    assert captured["target"] == pytest.approx({"BTC": 750.0, "ETH": -750.0})


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_propr_read_only_client_blocks_writes_before_transport(monkeypatch, method):
    from scripts.propr_client import ProprClient, ProprError

    def forbidden_transport(*_args, **_kwargs):
        raise AssertionError("network transport reached")

    monkeypatch.setattr("scripts.propr_client.requests.request", forbidden_transport)
    client = ProprClient("paper-key", read_only=True)
    with pytest.raises(ProprError, match="client read-only"):
        client._req(method, "/accounts/paper-1/orders")
