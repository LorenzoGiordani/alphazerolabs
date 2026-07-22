import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _attempt(account_id="competition-1", *, balance=50_000, slug="lighter-tournament"):
    return {
        "accountId": account_id,
        "status": "active",
        "competitionId": "urn:prp-competition:XSLPfvuHDUtT",
        "challenge": {"slug": slug, "initialBalance": balance},
    }


def _account(balance=50_000, unrealized=0):
    return {"balance": str(balance), "totalUnrealizedPnl": str(unrealized)}


def _position(
    asset="BTC",
    side="long",
    *,
    quantity="1",
    notional="100",
    mark="100",
    entry="100",
):
    return {
        "positionId": f"pos-{asset}", "base": asset, "positionSide": side,
        "quantity": quantity, "markPrice": mark, "entryPrice": entry,
        "notionalValue": notional,
        "unrealizedPnl": "0",
    }


def _state(competition, now, **updates):
    state = competition._fresh_state("competition-1", 50_000, now)
    state.update(updates)
    return state


def test_manage_kill_switch_blocks_before_client(monkeypatch):
    import scripts.propr_competition as competition

    monkeypatch.delenv("PROPR_COMPETITION_AUTOMANAGE_ENABLED", raising=False)
    monkeypatch.setattr(
        competition, "ProprClient",
        lambda *_args, **_kwargs: pytest.fail("client reached while disabled"),
    )

    assert competition.manage() == {"mode": "disabled", "writes": 0}


def test_manage_before_start_blocks_before_client(monkeypatch):
    import scripts.propr_competition as competition

    monkeypatch.setenv("PROPR_COMPETITION_AUTOMANAGE_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 23, 12, 59, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        competition, "ProprClient",
        lambda *_args, **_kwargs: pytest.fail("client reached before start"),
    )

    assert competition.manage() == {"mode": "waiting", "writes": 0}


def test_automanage_requires_independent_guard_switch_before_client(monkeypatch):
    import scripts.propr_competition as competition

    monkeypatch.setenv("PROPR_COMPETITION_AUTOMANAGE_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "false")
    monkeypatch.setattr(
        competition, "ProprClient",
        lambda *_args, **_kwargs: pytest.fail("client reached without guard switch"),
    )

    with pytest.raises(competition.ProprError, match="guard competition disabilitato"):
        competition.manage()


@pytest.mark.parametrize(
    ("attempt", "message"),
    [
        (_attempt(account_id="wrong"), "account competition inatteso"),
        (_attempt(balance=5_000), "balance iniziale competition inatteso"),
        (_attempt(slug="free-trial"), "rifiutato account Free Trial"),
        ({**_attempt(), "competitionId": "other"}, "competition id inatteso"),
        ({key: value for key, value in _attempt().items() if key != "competitionId"},
         "competition id inatteso"),
    ],
)
def test_attempt_validation_is_fail_closed(attempt, message):
    import scripts.propr_competition as competition

    with pytest.raises(competition.ProprError, match=message):
        competition._validate_attempt(attempt, "competition-1")


def test_check_uses_read_only_client_and_never_orders(tmp_path, monkeypatch):
    import scripts.propr_competition as competition

    class ReadOnlyClient:
        def __init__(self, *, read_only=False):
            assert read_only is True
            self.active_attempt = _attempt()

        def setup(self, **kwargs):
            assert kwargs == {"expected_account_id": "competition-1"}

        def get_positions(self):
            return []

        def get_account(self):
            return _account()

        def get_active_orders(self):
            return []

        def create_order(self, **_kwargs):
            pytest.fail("read-only check attempted an order")

    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(competition, "ProprClient", ReadOnlyClient)
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")
    result = competition.check()

    assert result["writes"] == 0
    assert result["equity"] == 50_000
    assert json.loads(competition.STATUS_PATH.read_text())["mode"] == "check"


def test_target_is_frozen_tsmom_with_bounded_gross(monkeypatch):
    import scripts.propr_competition as competition

    signals = pd.Series({
        "BTC": 0.1, "ETH": 0.2, "SOL": -0.1,
        "XRP": -0.2, "SUI": 0.3, "NEAR": -0.3,
    })
    prices = {asset: 100.0 for asset in competition.SYMBOLS}
    monkeypatch.setattr(competition, "trailing_returns", lambda *_args: (signals, prices))

    target, observed_prices = competition._target(50_000)

    assert set(target) == set(competition.SYMBOLS)
    assert sum(abs(value) for value in target.values()) == pytest.approx(15_000)
    assert competition.GROSS * float(competition.STOP_DISTANCE) <= competition.DAILY_STOP_PCT
    assert target["BTC"] > 0 and target["SOL"] < 0
    assert observed_prices == prices


def test_guard_flattens_at_end_even_when_automanage_is_off(tmp_path, monkeypatch):
    import scripts.propr_competition as competition

    events = []

    class Client:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()
            self.positions = [_position()]

        def setup(self, **kwargs):
            assert kwargs == {"expected_account_id": "competition-1"}

        def get_positions(self):
            return list(self.positions)

        def get_account(self):
            return _account()

        def get_active_orders(self):
            return []

    def fake_flatten(client, positions):
        events.append(("flatten", [position["base"] for position in positions]))
        client.positions = []
        return [{"asset": "BTC", "action": "flatten",
                 "resp": [{"orderId": "close-1", "status": "filled"}]}]

    monkeypatch.delenv("PROPR_COMPETITION_AUTOMANAGE_ENABLED", raising=False)
    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 30, 11, 10, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(competition, "ProprClient", Client)
    monkeypatch.setattr(competition, "flatten", fake_flatten)
    monkeypatch.setattr(
        competition, "_target", lambda *_args: pytest.fail("signal reached in flatten window"),
    )
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(competition, "JOURNAL_PATH", tmp_path / "journal.jsonl")
    state = _state(
        competition,
        datetime(2026, 7, 29, 11, 10, tzinfo=timezone.utc),
        last_rebalance_ts="2026-07-29T11:10:00+00:00",
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
        expected_quantities={"BTC": "1"},
        last_target={"BTC": 100.0},
    )
    competition.STATE_PATH.write_text(json.dumps(state))

    result = competition.guard()

    assert result == {"mode": "halted", "reason": "scheduled_end_flatten", "positions": 0}
    assert events == [("flatten", ["BTC"])]


def test_rebalance_timeout_after_write_is_guarded_and_flattened(tmp_path, monkeypatch):
    import scripts.propr_competition as competition

    events = []

    class Client:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()
            self.positions = []

        def setup(self, **kwargs):
            assert kwargs == {"expected_account_id": "competition-1"}

        def get_positions(self):
            return list(self.positions)

        def get_account(self):
            return _account()

        def get_active_orders(self):
            return []

    def fake_guard(_client, positions):
        events.append(("guard", len(positions)))
        return []

    def fake_rebalance(client, *_args):
        events.append(("rebalance_write",))
        client.positions = [_position()]
        raise TimeoutError("response lost after fill")

    def fake_flatten_cleanup(client, positions, reason):
        events.append(("flatten", reason, len(positions)))
        client.positions = []

    monkeypatch.setenv("PROPR_COMPETITION_AUTOMANAGE_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(competition, "ProprClient", Client)
    monkeypatch.setattr(competition, "_create_missing_stops", fake_guard)
    monkeypatch.setattr(competition, "rebalance", fake_rebalance)
    monkeypatch.setattr(competition, "_flatten_and_cleanup", fake_flatten_cleanup)
    monkeypatch.setattr(competition, "_target", lambda *_args: ({"BTC": 100.0}, {"BTC": 100.0}))
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(competition, "JOURNAL_PATH", tmp_path / "journal.jsonl")

    with pytest.raises(competition.ProprError, match="rebalance_recovery"):
        competition.manage()

    assert events == [
        ("guard", 0),
        ("rebalance_write",),
        ("guard", 1),
        ("flatten", "rebalance_recovery", 1),
    ]
    state = json.loads(competition.STATE_PATH.read_text())
    assert state["halted_today"] is True
    assert state["permanently_halted"] is True
    assert state["expected_assets"] == []
    assert json.loads(competition.STATUS_PATH.read_text())["mode"] == "error"


def test_journal_failure_after_order_triggers_recovery_flatten(tmp_path, monkeypatch):
    import scripts.propr_competition as competition

    events = []

    class Client:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()
            self.positions = []

        def setup(self, **_kwargs):
            return None

        def get_positions(self):
            return list(self.positions)

        def get_account(self):
            return _account()

        def get_active_orders(self):
            return []

    def fake_rebalance(client, *_args):
        client.positions = [_position()]
        events.append("order")
        return [{"asset": "BTC", "action": "adjust",
                 "resp": [{"orderId": "order-1", "status": "filled"}]}]

    def fake_flatten(client, positions, reason):
        events.append(("flatten", reason, len(positions)))
        client.positions = []

    monkeypatch.setenv("PROPR_COMPETITION_AUTOMANAGE_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(competition, "ProprClient", Client)
    monkeypatch.setattr(competition, "_create_missing_stops", lambda *_args: [])
    monkeypatch.setattr(competition, "rebalance", fake_rebalance)
    monkeypatch.setattr(
        competition, "_append_journal",
        lambda *_args: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(competition, "_flatten_and_cleanup", fake_flatten)
    monkeypatch.setattr(competition, "_target", lambda *_args: ({"BTC": 100.0}, {"BTC": 100.0}))
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")

    with pytest.raises(competition.ProprError, match="rebalance_recovery"):
        competition.manage()

    assert events == ["order", ("flatten", "rebalance_recovery", 1)]
    assert json.loads(competition.STATE_PATH.read_text())["permanently_halted"] is True


def test_nonfinite_target_is_blocked_before_any_order(tmp_path, monkeypatch):
    import scripts.propr_competition as competition

    events = []

    class Client:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()

        def setup(self, **_kwargs):
            return None

        def get_positions(self):
            return []

        def get_account(self):
            return _account()

        def get_active_orders(self):
            return []

    monkeypatch.setenv("PROPR_COMPETITION_AUTOMANAGE_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(competition, "ProprClient", Client)
    monkeypatch.setattr(competition, "_create_missing_stops", lambda *_args: [])
    monkeypatch.setattr(
        competition,
        "_flatten_and_cleanup",
        lambda _client, positions, reason: events.append(("flatten", reason, len(positions))),
    )
    monkeypatch.setattr(competition, "_target", lambda *_args: ({"BTC": float("nan")}, {"BTC": 100.0}))
    monkeypatch.setattr(
        competition,
        "rebalance",
        lambda *_args: pytest.fail("non-finite target reached order path"),
    )
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")

    with pytest.raises(competition.ProprError, match="rebalance_recovery"):
        competition.manage()

    assert events == [("flatten", "rebalance_recovery", 0)]


def test_flatten_requires_empty_position_readback(tmp_path, monkeypatch):
    import scripts.propr_competition as competition

    class Client:
        def get_positions(self):
            return [_position()]

    monkeypatch.setattr(
        competition, "flatten",
        lambda *_args: [{"asset": "BTC", "action": "flatten",
                         "resp": [{"orderId": "close-1", "status": "filled"}]}],
    )
    monkeypatch.setattr(competition.time, "sleep", lambda *_args: None)
    monkeypatch.setattr(competition, "JOURNAL_PATH", tmp_path / "journal.jsonl")

    with pytest.raises(competition.ProprError, match="flatten competition non confermato"):
        competition._flatten_checked(Client(), [_position()], "test")


def test_recovery_retries_transient_position_readback(tmp_path, monkeypatch):
    import scripts.propr_competition as competition

    events = []

    class Client:
        def __init__(self):
            self.readbacks = 0

        def get_positions(self):
            self.readbacks += 1
            if self.readbacks == 1:
                raise TimeoutError("temporary")
            return [_position()]

        def get_account(self):
            return _account()

    client = Client()
    state = _state(competition, datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc))
    monkeypatch.setattr(competition, "_create_missing_stops", lambda *_args: events.append("guard"))
    monkeypatch.setattr(
        competition,
        "_flatten_and_cleanup",
        lambda *_args: events.append("flatten"),
    )
    monkeypatch.setattr(competition.time, "sleep", lambda *_args: None)
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")

    with pytest.raises(competition.ProprError, match="recovery verified flat"):
        competition._recover_after_write(
            client,
            state,
            datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
            "test_recovery",
            TimeoutError("original"),
        )

    assert client.readbacks == 2
    assert events == ["guard", "flatten"]


@pytest.mark.parametrize(
    ("starting_positions", "balance"),
    [([_position()], 50_000), ([_position("DOGE")], 50_000), ([], 49_999)],
)
def test_no_state_unsafe_account_guard_recovers_and_halts(
    tmp_path,
    monkeypatch,
    starting_positions,
    balance,
):
    import scripts.propr_competition as competition

    events = []

    class Client:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()
            self.positions = list(starting_positions)

        def setup(self, **_kwargs):
            return None

        def get_positions(self):
            return list(self.positions)

        def get_account(self):
            return _account(balance)

        def get_active_orders(self):
            return []

    def fake_flatten(client, positions, reason):
        events.append((reason, len(positions)))
        client.positions = []

    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(competition, "ProprClient", Client)
    monkeypatch.setattr(competition, "_create_missing_stops", lambda *_args: [])
    monkeypatch.setattr(competition, "_flatten_and_cleanup", fake_flatten)
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")

    with pytest.raises(competition.ProprError, match="first_activation_nonflat"):
        competition.guard()

    state = json.loads(competition.STATE_PATH.read_text())
    assert events == [("first_activation_nonflat", len(starting_positions))]
    assert state["permanently_halted"] is True
    assert state["expected_quantities"] == {}


@pytest.mark.parametrize(
    "corrupt_update",
    [
        {"expected_quantities": {"BTC": "bad"}},
        {"day_start_equity": "nan"},
        {"high_water_mark": "nan"},
    ],
)
def test_semantically_corrupt_state_routes_to_recovery(
    tmp_path,
    monkeypatch,
    corrupt_update,
):
    import scripts.propr_competition as competition

    events = []

    class Client:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()
            self.positions = [_position()]

        def setup(self, **_kwargs):
            return None

        def get_positions(self):
            return list(self.positions)

        def get_account(self):
            return _account()

        def get_active_orders(self):
            return []

    def fake_flatten(client, positions, reason):
        events.append((reason, len(positions)))
        client.positions = []

    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(competition, "ProprClient", Client)
    monkeypatch.setattr(competition, "_create_missing_stops", lambda *_args: [])
    monkeypatch.setattr(competition, "_flatten_and_cleanup", fake_flatten)
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")
    state = _state(
        competition,
        datetime(2026, 7, 23, 13, 0, tzinfo=timezone.utc),
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
        expected_quantities={"BTC": "1"},
        last_target={"BTC": 100.0},
        last_rebalance_ts="2026-07-23T13:00:00+00:00",
    )
    state.update(corrupt_update)
    competition.STATE_PATH.write_text(json.dumps(state))

    with pytest.raises(competition.ProprError, match="state_unreadable"):
        competition.guard()

    assert events == [("state_unreadable", 1)]
    assert json.loads(competition.STATE_PATH.read_text())["permanently_halted"] is True


@pytest.mark.parametrize(
    "bad_position",
    [
        {**_position(), "entryPrice": None},
        _position(notional="nan"),
    ],
)
def test_invalid_position_schema_routes_to_recovery(
    tmp_path,
    monkeypatch,
    bad_position,
):
    import scripts.propr_competition as competition

    events = []

    class Client:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()
            self.positions = [bad_position]

        def setup(self, **_kwargs):
            return None

        def get_positions(self):
            return list(self.positions)

        def get_account(self):
            return _account()

        def get_active_orders(self):
            return []

    def fake_flatten(client, positions, reason):
        events.append((reason, len(positions)))
        client.positions = []

    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(competition, "ProprClient", Client)
    monkeypatch.setattr(competition, "_create_missing_stops", lambda *_args: [])
    monkeypatch.setattr(competition, "_flatten_and_cleanup", fake_flatten)
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")
    competition.STATE_PATH.write_text(json.dumps(_state(
        competition,
        datetime(2026, 7, 23, 13, 0, tzinfo=timezone.utc),
    )))

    with pytest.raises(competition.ProprError, match="state_or_position_invalid"):
        competition.guard()

    assert events == [("state_or_position_invalid", 1)]
    assert json.loads(competition.STATE_PATH.read_text())["permanently_halted"] is True


def test_stop_contract_rejects_far_trigger_even_with_expected_intent():
    import scripts.propr_competition as competition

    position = _position()
    plan = competition._stop_plan(position)
    order = {
        "orderId": "stop-1",
        "intentId": plan["intent_id"],
        "positionId": plan["position_id"],
        "type": "stop_market",
        "side": plan["side"],
        "positionSide": plan["position_side"],
        "quantity": plan["quantity"],
        "triggerPrice": "50",
        "reduceOnly": True,
        "closePosition": True,
    }

    assert competition._is_exact_protection(position, order) is False


def test_crossed_stop_causes_guard_recovery_flatten(tmp_path, monkeypatch):
    import scripts.propr_competition as competition

    position = _position(mark="95", entry="100", notional="95")
    plan = competition._stop_plan(position)
    order = {
        "orderId": "stop-1",
        "intentId": plan["intent_id"],
        "positionId": plan["position_id"],
        "type": "stop_market",
        "side": plan["side"],
        "positionSide": plan["position_side"],
        "quantity": plan["quantity"],
        "triggerPrice": plan["trigger_price"],
        "reduceOnly": True,
        "closePosition": True,
    }
    events = []

    class Client:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()
            self.positions = [position]

        def setup(self, **_kwargs):
            return None

        def get_positions(self):
            return list(self.positions)

        def get_account(self):
            return _account()

        def get_active_orders(self):
            return [order]

    def fake_flatten(client, positions, reason):
        events.append((reason, len(positions)))
        client.positions = []

    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(competition, "ProprClient", Client)
    monkeypatch.setattr(competition, "_flatten_and_cleanup", fake_flatten)
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")
    state = _state(
        competition,
        datetime(2026, 7, 23, 13, 0, tzinfo=timezone.utc),
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
        expected_quantities={"BTC": "1"},
        last_target={"BTC": 100.0},
        last_rebalance_ts="2026-07-23T13:00:00+00:00",
    )
    competition.STATE_PATH.write_text(json.dumps(state))

    with pytest.raises(competition.ProprError, match="guard_failure"):
        competition.guard()

    assert events == [("guard_failure", 1)]
    assert json.loads(competition.STATE_PATH.read_text())["permanently_halted"] is True


def test_midnight_rollover_preserves_book_and_rebalance_clock():
    import scripts.propr_competition as competition

    state = _state(
        competition,
        datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
        last_rebalance_ts="2026-07-23T13:10:00+00:00",
        last_equity=50_000,
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
    )
    position = _position()
    competition._roll_day(
        state, [position], 49_900,
        datetime(2026, 7, 24, 0, 10, tzinfo=timezone.utc),
    )

    assert state["last_rebalance_ts"] == "2026-07-23T13:10:00+00:00"
    assert state["expected_sides"] == {"BTC": "long"}
    assert state["day_start_equity"] == 50_000
    assert competition._due(
        state, datetime(2026, 7, 24, 0, 10, tzinfo=timezone.utc)
    ) is False


def test_midnight_rollover_does_not_hide_native_stop_drift():
    import scripts.propr_competition as competition

    state = _state(
        competition,
        datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
        last_equity=50_000,
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
    )
    now = datetime(2026, 7, 24, 0, 10, tzinfo=timezone.utc)
    competition._roll_day(state, [], 49_900, now)

    assert competition._risk_reason(state, [], 49_900, now) == (
        "native_stop_or_external_drift", True
    )


def test_reconcile_detects_wrong_side_and_notional():
    import scripts.propr_competition as competition

    positions = [
        _position("BTC", "short", notional="100"),
        _position("ETH", "short", notional="50"),
    ]
    errors = competition._reconcile_target(positions, {"BTC": 100.0, "ETH": -100.0})

    assert "BTC:side" in errors
    assert any(error.startswith("ETH:notional") for error in errors)


def test_runtime_book_drift_detects_large_notional_change_with_same_side_and_quantity():
    import scripts.propr_competition as competition

    state = _state(
        competition,
        datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
        expected_quantities={"BTC": "1"},
        last_target={"BTC": 2500.0},
    )

    assert competition._book_drift(
        state,
        [_position(quantity="1", notional="7500", mark="7500")],
    ) is True


def test_runtime_book_drift_rejects_missing_target_for_nonempty_book():
    import scripts.propr_competition as competition

    state = _state(
        competition,
        datetime(2026, 7, 23, 13, 10, tzinfo=timezone.utc),
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
        expected_quantities={"BTC": "1"},
    )

    assert competition._book_drift(state, [_position()]) is True


def test_workflow_keeps_competition_dormant_by_default():
    workflow = (ROOT / ".github/workflows/propr-competition.yml").read_text()

    assert "PROPR_COMPETITION_GUARD_ENABLED: ${{ vars.PROPR_COMPETITION_GUARD_ENABLED }}" in workflow
    assert "PROPR_COMPETITION_AUTOMANAGE_ENABLED: ${{ vars.PROPR_COMPETITION_AUTOMANAGE_ENABLED }}" in workflow
    assert "env.PROPR_COMPETITION_GUARD_ENABLED == 'true'" in workflow
    assert "env.PROPR_COMPETITION_AUTOMANAGE_ENABLED == 'true'" in workflow
    assert workflow.count("inputs.action != 'check'") == 2
    assert "uv run scripts/propr_competition.py --guard" in workflow
    assert "uv run scripts/propr_competition.py --manage" in workflow
    assert "GUARD_OUTCOME: ${{ steps.guard.outcome }}" in workflow
    assert "MANAGE_OUTCOME: ${{ steps.manage.outcome }}" in workflow
    assert "PROPR_COMPETITION_ACCOUNT_ID: ${{ vars.PROPR_COMPETITION_ACCOUNT_ID }}" in workflow
    assert "paper/propr_competition_state.json" in workflow
    assert "propr_competition" not in (ROOT / ".github/workflows/paper-run.yml").read_text()
