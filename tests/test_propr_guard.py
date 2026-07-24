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
        "challenge": {
            "slug": slug,
            "initialBalance": balance,
            "phases": [{
                "profitTargetPercent": 10,
                "maxDailyLossPercent": 3,
                "maxDrawdownPercent": 6,
            }],
        },
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


def _stop(order_id, position, created_at):
    is_long = position["positionSide"] == "long"
    mark = float(position["markPrice"])
    return {
        "orderId": order_id,
        "intentId": f"intent-{order_id}",
        "positionId": position["positionId"],
        "asset": position["base"],
        "type": "stop_market",
        "side": "sell" if is_long else "buy",
        "positionSide": "short" if is_long else "long",
        "quantity": position["quantity"],
        "triggerPrice": str(mark * (0.96 if is_long else 1.04)),
        "reduceOnly": True,
        "closePosition": True,
        "createdAt": created_at,
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
        side="sell", position_side="short", order_type="stop_market", asset="BTC",
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
    assert (order["side"], order["positionSide"]) == ("sell", "short")
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


def test_execute_requires_paper_evidence_before_client(monkeypatch):
    import scripts.propr_guard as guard
    from scripts.propr_client import ProprError

    monkeypatch.setenv("PROPR_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_EXPECTED_ACCOUNT_ID", "paper-1")
    monkeypatch.setattr(
        guard,
        "_require_write_evidence",
        lambda _account_id: (_ for _ in ()).throw(
            ProprError("evidenza paper non verificata")),
    )
    monkeypatch.setattr(
        guard,
        "ProprClient",
        lambda **_kwargs: pytest.fail("client reached before evidence gate"),
    )

    with pytest.raises(ProprError, match="evidenza paper non verificata"):
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

        def get_active_orders(self):
            return [_stop(
                "stop-btc",
                _position("BTC", "pos-btc", "long", "100", "2"),
                "2026-07-24T09:00:00Z",
            )]

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
    assert plan["position_side"] == "long"
    assert plan["trigger_price"] == "208"
    assert plan["intent_id"] == guard._intent_id(
        _position("ETH", "pos-eth", "short", "200", "3")
    )


def test_guard_intent_is_stable_for_same_position_across_market_changes():
    import scripts.propr_guard as guard

    first, _ = guard._build_plan(
        [_position("ETH", "pos-eth", "short", "200", "3")], [], "*"
    )
    changed, _ = guard._build_plan(
        [_position("ETH", "pos-eth", "short", "220", "4")], [], "*"
    )
    flipped, _ = guard._build_plan(
        [_position("ETH", "pos-eth", "long", "220", "4")], [], "*"
    )

    assert first[0]["trigger_price"] != changed[0]["trigger_price"]
    assert first[0]["quantity"] != changed[0]["quantity"]
    assert first[0]["intent_id"] == changed[0]["intent_id"]
    assert first[0]["intent_id"] != flipped[0]["intent_id"]


def test_wrong_side_stop_does_not_count_as_protection():
    import scripts.propr_guard as guard

    position = _position("ETH", "pos-eth", "short", "200", "3")
    wrong = _stop("wrong", position, "2026-07-24T09:00:00Z")
    wrong["positionSide"] = "short"
    plans, skipped = guard._build_plan([position], [wrong], "*")
    assert skipped == 0
    assert len(plans) == 1
    assert plans[0]["side"] == "buy"
    assert plans[0]["position_side"] == "long"


@pytest.mark.parametrize("updates", [
    {"asset": "ETH"},
    {"quantity": "NaN"},
    {"quantity": "0"},
    {"triggerPrice": "NaN"},
    {"triggerPrice": "0"},
    {"triggerPrice": "101"},
])
def test_protective_order_rejects_wrong_asset_or_invalid_risk_fields(updates):
    import scripts.propr_guard as guard

    position = _position("BTC", "pos-btc", "long", "100", "2")
    order = _stop("stop-btc", position, "2026-07-24T09:00:00Z")
    order.update(updates)

    assert guard._is_protective_order(position, order) is False


def test_protective_order_accepts_stale_positive_quantity_with_close_position():
    import scripts.propr_guard as guard

    position = _position("BTC", "pos-btc", "long", "100", "2")
    order = _stop("stop-btc", position, "2026-07-24T09:00:00Z")
    order["quantity"] = "999"

    assert guard._is_protective_order(position, order) is True


def test_reconciliation_requires_one_stop_per_position_without_orphans():
    import scripts.propr_guard as guard

    btc = _position("BTC", "pos-btc")
    eth = _position("ETH", "pos-eth", "short")
    exact = guard.reconciliation_summary(
        [btc, eth],
        [_stop("btc", btc, "2026-07-24T09:00:00Z"),
         _stop("eth", eth, "2026-07-24T09:00:00Z")],
    )
    assert exact["exactly_one_per_position"] is True

    duplicate = guard.reconciliation_summary(
        [btc, eth],
        [_stop("btc-old", btc, "2026-07-24T09:00:00Z"),
         _stop("btc-new", btc, "2026-07-24T09:01:00Z"),
         _stop("eth", eth, "2026-07-24T09:00:00Z"),
         _stop("orphan", _position("SUI", "pos-gone"), "2026-07-24T09:00:00Z"),
         {"orderId": "limit", "type": "limit"}],
    )
    assert duplicate["duplicate_protective_orders"] == 1
    assert duplicate["unmatched_protective_orders"] == 1
    assert duplicate["unexpected_active_orders"] == 1
    assert duplicate["exactly_one_per_position"] is False


def test_guard_rejects_duplicate_plus_missing_before_first_write(tmp_path, monkeypatch):
    import scripts.propr_guard as guard
    from scripts.propr_client import ProprError

    btc = _position("BTC", "pos-btc")
    eth = _position("ETH", "pos-eth")

    class FakeClient:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()

        def setup(self, **_kwargs):
            return "paper-1"

        def get_positions(self):
            return [btc, eth]

        def get_active_orders(self):
            return [
                _stop("btc-old", btc, "2026-07-24T09:00:00Z"),
                _stop("btc-new", btc, "2026-07-24T09:01:00Z"),
            ]

        def create_order(self, **_kwargs):
            pytest.fail("write reached with duplicate preflight")

    monkeypatch.setattr(guard, "ProprClient", FakeClient)
    monkeypatch.setattr(guard, "_require_write_evidence", lambda _account_id: {})
    monkeypatch.setattr(guard, "JOURNAL", tmp_path / "guard.jsonl")
    monkeypatch.setenv("PROPR_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_EXPECTED_ACCOUNT_ID", "paper-1")

    with pytest.raises(ProprError, match="preflight stop non sicuro"):
        guard.main(execute=True)

    assert not guard.JOURNAL.exists()


def test_execute_rejects_more_than_eight_stops_before_first_write(tmp_path, monkeypatch):
    import scripts.propr_guard as guard
    from scripts.propr_client import ProprError

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

        def get_active_orders(self):
            events.append(("orders", "active"))
            return []

        def create_order(self, **kwargs):
            events.append(("write", kwargs))
            return [{"orderId": kwargs["position_id"], "intentId": kwargs["intent_id"],
                     "status": "open"}]

    monkeypatch.setattr(guard, "ProprClient", FakeClient)
    monkeypatch.setattr(guard, "_require_write_evidence", lambda _account_id: {})
    monkeypatch.setattr(guard, "JOURNAL", tmp_path / "guard.jsonl")
    monkeypatch.setenv("PROPR_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_EXPECTED_ACCOUNT_ID", "paper-1")
    monkeypatch.setenv("PROPR_GUARD_CANARY_ASSET", "*")
    with pytest.raises(ProprError, match="10 stop > cap 8"):
        guard.main(execute=True)

    writes = [event for event in events if event[0] == "write"]
    assert writes == []
    assert [event[0] for event in events[:3]] == ["setup", "positions", "orders"]
    assert not guard.JOURNAL.exists()


def test_guard_rejects_unverifiable_create_response(tmp_path, monkeypatch):
    import scripts.propr_guard as guard
    from scripts.propr_client import ProprError

    class FakeClient:
        def __init__(self, *, read_only=False):
            self.active_attempt = _attempt()

        def setup(self, **_kwargs):
            return "paper-1"

        def get_positions(self):
            return [_position()]

        def get_active_orders(self):
            return []

        def create_order(self, **_kwargs):
            return []

    monkeypatch.setattr(guard, "ProprClient", FakeClient)
    monkeypatch.setattr(guard, "_require_write_evidence", lambda _account_id: {})
    monkeypatch.setattr(guard, "JOURNAL", tmp_path / "guard.jsonl")
    monkeypatch.setenv("PROPR_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_EXPECTED_ACCOUNT_ID", "paper-1")

    with pytest.raises(ProprError, match="risposta creazione stop non verificabile"):
        guard.main(execute=True)

    assert not guard.JOURNAL.exists()


def test_dedupe_keeps_oldest_protection_per_position():
    import scripts.propr_guard as guard

    btc = _position("BTC", "pos-btc")
    eth = _position("ETH", "pos-eth", "short")
    orders = [
        _stop("btc-old", btc, "2026-07-21T19:58:00Z"),
        _stop("btc-new", btc, "2026-07-21T20:03:00Z"),
        _stop("eth-old", eth, "2026-07-21T19:58:00Z"),
        _stop("eth-new", eth, "2026-07-21T20:03:00Z"),
    ]

    plan = guard._build_dedupe_plan([btc, eth], orders)

    assert {item["order_id"] for item in plan} == {"btc-new", "eth-new"}
    assert {item["kept_order_id"] for item in plan} == {"btc-old", "eth-old"}


def test_dedupe_cancels_exact_expected_count_and_journals(tmp_path, monkeypatch):
    import scripts.propr_guard as guard

    positions = [_position(asset, f"pos-{asset.lower()}") for asset in ("BTC", "ETH", "SOL")]
    orders = []
    for position in positions:
        orders.extend([
            _stop(f"{position['base']}-old", position, "2026-07-21T19:58:00Z"),
            _stop(f"{position['base']}-new", position, "2026-07-21T20:03:00Z"),
        ])
    cancelled = []

    class FakeClient:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()

        def setup(self, **kwargs):
            assert kwargs == {
                "expected_account_id": "paper-1", "expected_challenge_slug": "free-trial"}
            return "paper-1"

        def get_positions(self):
            return positions

        def get_active_orders(self):
            return orders

        def cancel_order(self, order_id):
            cancelled.append(order_id)
            return {"orderId": order_id, "status": "cancelled"}

    monkeypatch.setattr(guard, "ProprClient", FakeClient)
    monkeypatch.setattr(guard, "_require_write_evidence", lambda _account_id: {})
    monkeypatch.setattr(guard, "JOURNAL", tmp_path / "guard.jsonl")
    monkeypatch.setenv("PROPR_DEDUPE_ENABLED", "true")
    monkeypatch.setenv("PROPR_GUARD_ENABLED", "false")
    monkeypatch.setenv("PROPR_AUTOMANAGE_ENABLED", "false")
    monkeypatch.setenv("PROPR_EXPECTED_ACCOUNT_ID", "paper-1")

    result = guard.dedupe(expected_duplicates=3)

    assert set(cancelled) == {"BTC-new", "ETH-new", "SOL-new"}
    assert result["cancelled_count"] == 3
    journal = [json.loads(line) for line in guard.JOURNAL.read_text().splitlines()]
    assert journal[0]["status"] == "deduped"


def test_dedupe_count_mismatch_fails_before_cancel(tmp_path, monkeypatch):
    import scripts.propr_guard as guard
    from scripts.propr_client import ProprError

    position = _position()

    class FakeClient:
        def __init__(self, *, read_only=False):
            self.active_attempt = _attempt()

        def setup(self, **_kwargs):
            return "paper-1"

        def get_positions(self):
            return [position]

        def get_active_orders(self):
            return [_stop("old", position, "2026-07-21T19:58:00Z"),
                    _stop("new", position, "2026-07-21T20:03:00Z")]

        def cancel_order(self, _order_id):
            pytest.fail("cancel reached before exact-count validation")

    monkeypatch.setattr(guard, "ProprClient", FakeClient)
    monkeypatch.setattr(guard, "_require_write_evidence", lambda _account_id: {})
    monkeypatch.setattr(guard, "JOURNAL", tmp_path / "guard.jsonl")
    monkeypatch.setenv("PROPR_DEDUPE_ENABLED", "true")
    monkeypatch.setenv("PROPR_GUARD_ENABLED", "false")
    monkeypatch.setenv("PROPR_AUTOMANAGE_ENABLED", "false")
    monkeypatch.setenv("PROPR_EXPECTED_ACCOUNT_ID", "paper-1")

    with pytest.raises(ProprError, match="attesi 3, trovati 1"):
        guard.dedupe(expected_duplicates=3)

    assert not guard.JOURNAL.exists()


def test_client_reads_and_deduplicates_every_active_order_page(monkeypatch):
    from scripts.propr_client import ACTIVE_ORDER_STATUSES, ORDER_PAGE_LIMIT, ProprClient

    pending = [
        {"orderId": f"order-{index}", "status": "pending"}
        for index in range(ORDER_PAGE_LIMIT + 1)
    ]
    calls = []
    client = ProprClient("paper-key", read_only=True)
    client.account_id = "paper-1"

    def fake_req(method, path, *, params):
        calls.append((method, path, params.copy()))
        status, offset = params["status"], params["offset"]
        source = pending if status == "pending" else (
            [{"orderId": "order-0", "status": "open"}] if status == "open" else []
        )
        page = source[offset:offset + params["limit"]]
        return {"data": page, "total": len(source), "offset": offset}

    monkeypatch.setattr(client, "_req", fake_req)

    orders = client.get_active_orders()

    assert len(orders) == len(pending)
    assert {call[2]["status"] for call in calls} == set(ACTIVE_ORDER_STATUSES)
    assert any(call[2]["offset"] == ORDER_PAGE_LIMIT for call in calls)


def test_client_fails_closed_on_incomplete_order_page(monkeypatch):
    from scripts.propr_client import ProprClient, ProprError

    client = ProprClient("paper-key", read_only=True)
    client.account_id = "paper-1"
    repeated = [{"orderId": f"order-{index}"} for index in range(20)]
    monkeypatch.setattr(client, "_req", lambda *_args, **_kwargs: {"data": repeated})

    with pytest.raises(ProprError, match="paginazione ordini duplicata"):
        client.get_active_orders()


def test_client_paginates_when_optional_metadata_is_omitted(monkeypatch):
    from scripts.propr_client import ORDER_PAGE_LIMIT, ProprClient

    pending = [{"orderId": f"order-{index}"} for index in range(ORDER_PAGE_LIMIT + 1)]
    client = ProprClient("paper-key", read_only=True)
    client.account_id = "paper-1"

    def fake_req(_method, _path, *, params):
        source = pending if params["status"] == "pending" else []
        offset = params["offset"]
        return {"data": source[offset:offset + params["limit"]]}

    monkeypatch.setattr(client, "_req", fake_req)

    assert len(client.get_active_orders()) == len(pending)


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
    monkeypatch.setattr(guard, "_require_write_evidence", lambda _account_id: {})
    monkeypatch.setenv("PROPR_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_EXPECTED_ACCOUNT_ID", "paper-1")
    with pytest.raises(ProprError, match="balance iniziale inatteso"):
        guard.main(execute=True)
