import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _attempt(account_id="paper-1", *, slug="free-trial", balance=5000):
    return {
        "accountId": account_id,
        "status": "active",
        "createdAt": "2026-07-17T10:00:00Z",
        "challenge": {"slug": slug, "initialBalance": balance},
    }


def _position(asset="BTC", position_id="pos-1", side="long", mark="100", quantity="2"):
    return {
        "base": asset,
        "positionId": position_id,
        "positionSide": side,
        "markPrice": mark,
        "quantity": quantity,
        "createdAt": "2026-07-17T10:00:00Z",
    }


def test_guard_cli_imports_from_repo_root():
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(root / "scripts/propr_guard.py"), "--help"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_client_pins_exact_active_account_and_challenge(monkeypatch):
    from scripts.propr_client import ProprClient, ProprError

    attempts = [_attempt("wrong", slug="paid"), _attempt("paper-1")]
    client = ProprClient("paper-key", read_only=True)
    monkeypatch.setattr(client, "_req", lambda *_args, **_kwargs: {"data": attempts})

    assert client.setup(expected_account_id="paper-1", expected_challenge_slug="free-trial") == "paper-1"
    assert client.active_attempt == attempts[1]

    other = ProprClient("paper-key", read_only=True)
    monkeypatch.setattr(other, "_req", lambda *_args, **_kwargs: {"data": attempts})
    with pytest.raises(ProprError, match="account attivo atteso non trovato"):
        other.setup(expected_account_id="missing", expected_challenge_slug="free-trial")


def test_client_builds_conditional_close_payload(monkeypatch):
    from scripts.propr_client import ProprClient

    captured = {}
    client = ProprClient("paper-key")
    client.account_id = "paper-1"

    def fake_req(method, path, **kwargs):
        captured.update(method=method, path=path, **kwargs)
        return {"data": [{"orderId": "order-1"}]}

    monkeypatch.setattr(client, "_req", fake_req)
    result = client.create_order(
        side="sell", position_side="long", order_type="stop_market", asset="BTC",
        quantity="2", reduce_only=True, close_position=True,
        intent_id="01INTENT", position_id="pos-1", trigger_price="96",
    )

    order = captured["json"]["orders"][0]
    assert (captured["method"], captured["path"]) == (
        "POST", "/accounts/paper-1/orders"
    )
    assert result == [{"orderId": "order-1"}]
    assert order["intentId"] == "01INTENT"
    assert order["positionId"] == "pos-1"
    assert order["triggerPrice"] == "96"
    assert order["timeInForce"] == "GTC"
    assert order["reduceOnly"] is True
    assert order["closePosition"] is True


def test_execute_requires_both_kill_switch_and_exact_account_before_client(monkeypatch):
    import scripts.propr_guard as guard
    from scripts.propr_client import ProprError

    monkeypatch.delenv("PROPR_GUARD_ENABLED", raising=False)
    monkeypatch.delenv("PROPR_EXPECTED_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(guard, "ProprClient", lambda **_kwargs: pytest.fail("client reached"))
    with pytest.raises(ProprError, match="guard disabilitato"):
        guard.main(execute=True)

    monkeypatch.setenv("PROPR_GUARD_ENABLED", "true")
    with pytest.raises(ProprError, match="PROPR_EXPECTED_ACCOUNT_ID"):
        guard.main(execute=True)


def test_read_only_plan_uses_canary_opposite_side_and_skips_existing(monkeypatch):
    import scripts.propr_guard as guard

    class FakeClient:
        def __init__(self, *, read_only=False):
            assert read_only is True
            self.active_attempt = _attempt()

        def setup(self, **kwargs):
            assert kwargs == {
                "expected_account_id": None,
                "expected_challenge_slug": "free-trial",
            }
            return "paper-1"

        def get_positions(self):
            return [
                _position("BTC", "pos-btc", "long", "100", "2"),
                _position("ETH", "pos-eth", "short", "200", "3"),
            ]

        def get_orders(self, status="open"):
            assert status == "open"
            return [{"positionId": "pos-btc", "type": "stop_market",
                     "side": "sell", "positionSide": "long",
                     "reduceOnly": True, "closePosition": True}]

        def create_order(self, **_kwargs):
            pytest.fail("read-only plan attempted a write")

    monkeypatch.setattr(guard, "ProprClient", FakeClient)
    monkeypatch.setenv("PROPR_GUARD_CANARY_ASSET", "*")
    result = guard.main()

    assert result["planned_count"] == 1
    assert result["skipped_existing"] == 1
    plan = result["plans"][0]
    assert plan["asset"] == "ETH"
    assert plan["side"] == "buy"
    assert plan["position_side"] == "short"
    assert plan["trigger_price"] == "208"
    assert plan["intent_id"] == guard._intent_id(
        _position("ETH", "pos-eth", "short", "200", "3"), "3", "208"
    )


def test_wrong_side_stop_does_not_count_as_protection():
    import scripts.propr_guard as guard

    position = _position("ETH", "pos-eth", "short", "200", "3")
    wrong = {"positionId": "pos-eth", "type": "stop_market", "side": "sell",
             "positionSide": "long", "reduceOnly": True, "closePosition": True}
    plans, skipped = guard._build_plan([position], [wrong], "*")
    assert skipped == 0
    assert len(plans) == 1
    assert plans[0]["side"] == "buy"
    assert plans[0]["position_side"] == "short"


def test_execute_plans_at_most_eight_before_writes_and_journals_actions(tmp_path, monkeypatch):
    import scripts.propr_guard as guard

    events = []

    class FakeClient:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()

        def setup(self, **kwargs):
            events.append(("setup", kwargs))
            return "paper-1"

        def get_positions(self):
            events.append(("positions",))
            return [_position(f"A{i:02}", f"pos-{i}") for i in range(10)]

        def get_orders(self, status="open"):
            events.append(("orders", status))
            return []

        def create_order(self, **kwargs):
            events.append(("write", kwargs))
            return [{"orderId": kwargs["position_id"]}]

    monkeypatch.setattr(guard, "ProprClient", FakeClient)
    monkeypatch.setattr(guard, "JOURNAL", tmp_path / "guard.jsonl")
    monkeypatch.setenv("PROPR_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_EXPECTED_ACCOUNT_ID", "paper-1")
    monkeypatch.setenv("PROPR_GUARD_CANARY_ASSET", "*")
    result = guard.main(execute=True)

    writes = [event for event in events if event[0] == "write"]
    assert len(writes) == guard.MAX_CREATES == 8
    assert [event[0] for event in events[:3]] == ["setup", "positions", "orders"]
    assert events[3][0] == "write"
    assert result["created_count"] == 8
    assert all(event[1]["reduce_only"] and event[1]["close_position"] for event in writes)
    assert all(event[1]["position_side"] == "long" for event in writes)
    journal = [json.loads(line) for line in guard.JOURNAL.read_text().splitlines()]
    assert len(journal) == 1
    assert journal[0]["status"] == "created"
    assert len(journal[0]["actions"]) == 8


def test_execute_rejects_non_5k_attempt_before_orders(monkeypatch):
    import scripts.propr_guard as guard
    from scripts.propr_client import ProprError

    class FakeClient:
        def __init__(self, *, read_only=False):
            self.active_attempt = _attempt(balance=10_000)

        def setup(self, **_kwargs):
            return "paper-1"

        def get_positions(self):
            pytest.fail("positions reached before challenge validation")

    monkeypatch.setattr(guard, "ProprClient", FakeClient)
    monkeypatch.setenv("PROPR_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_EXPECTED_ACCOUNT_ID", "paper-1")
    with pytest.raises(ProprError, match="balance iniziale inatteso"):
        guard.main(execute=True)
