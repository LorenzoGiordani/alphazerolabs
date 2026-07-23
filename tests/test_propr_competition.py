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
        "competition": {
            "competitionId": "urn:prp-competition:XSLPfvuHDUtT",
            "exchange": "hyperliquid",
            "currency": "USDC",
            "slug": "lighter-propr-trading-tournament",
            "initialBalance": str(balance),
            "startsAt": "2026-07-23T13:00:00.000Z",
            "endsAt": "2026-07-30T13:00:00.000Z",
        },
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
        ({
            **{key: value for key, value in _attempt().items() if key != "competitionId"},
            "competition": {
                **_attempt()["competition"],
                "competitionId": None,
            },
         },
         "competition id inatteso"),
        ({
            **_attempt(),
            "competition": {
                **_attempt()["competition"],
                "exchange": "other",
            },
         },
         "exchange competition inatteso"),
        ({
            **_attempt(),
            "competition": {
                **_attempt()["competition"],
                "slug": "other",
            },
         },
         "slug competition inatteso"),
        ({
            **_attempt(),
            "competition": {
                **_attempt()["competition"],
                "startsAt": "2026-07-23T14:00:00.000Z",
            },
         },
         "startsAt competition inatteso"),
    ],
)
def test_attempt_validation_is_fail_closed(attempt, message):
    import scripts.propr_competition as competition

    with pytest.raises(competition.ProprError, match=message):
        competition._validate_attempt(attempt, "competition-1")


def test_client_setup_competition_uses_exact_owned_account(monkeypatch):
    from scripts.propr_client import ProprClient

    client = ProprClient(api_key="test", read_only=True)
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/accounts/competition-1":
            return {"accountId": "urn:prp-account:competition-1", "balance": "50000"}
        if path == "/competitions/lighter-propr-trading-tournament":
            return _attempt()["competition"]
        raise AssertionError(path)

    monkeypatch.setattr(client, "_req", request)

    assert client.setup(
        expected_account_id="competition-1",
        expected_competition_id="urn:prp-competition:XSLPfvuHDUtT",
        expected_competition_slug="lighter-propr-trading-tournament",
    ) == "competition-1"
    assert client.active_attempt["challenge"]["initialBalance"] == "50000"
    assert calls == [
        ("GET", "/accounts/competition-1", {}),
        ("GET", "/competitions/lighter-propr-trading-tournament", {}),
    ]


@pytest.mark.parametrize(
    ("account", "message"),
    [
        ([], "account competition non accessibile"),
        ({}, "account competition non accessibile"),
        ({"balance": "50000"}, "account competition inatteso"),
        ({"accountId": "other", "balance": "50000"}, "account competition inatteso"),
    ],
)
def test_client_setup_competition_rejects_inaccessible_or_wrong_account(
    monkeypatch, account, message,
):
    from scripts.propr_client import ProprClient, ProprError

    client = ProprClient(api_key="test", read_only=True)

    def request(_method, path, **_kwargs):
        if path == "/accounts/competition-1":
            return account
        if path == "/competitions/lighter-propr-trading-tournament":
            return _attempt()["competition"]
        raise AssertionError(path)

    monkeypatch.setattr(client, "_req", request)

    with pytest.raises(ProprError, match=message):
        client.setup(
            expected_account_id="competition-1",
            expected_competition_id="urn:prp-competition:XSLPfvuHDUtT",
            expected_competition_slug="lighter-propr-trading-tournament",
        )


def test_check_uses_read_only_client_and_never_orders(tmp_path, monkeypatch):
    import scripts.propr_competition as competition

    class ReadOnlyClient:
        def __init__(self, *, read_only=False):
            assert read_only is True
            self.active_attempt = _attempt()

        def setup(self, **kwargs):
            assert kwargs == {
                "expected_account_id": "competition-1",
                "expected_competition_id": competition.COMPETITION_ID,
                "expected_competition_slug": competition.COMPETITION_SLUG,
            }

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
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")
    result = competition.check()

    assert result["writes"] == 0
    assert result["equity"] == 50_000
    assert json.loads(competition.STATUS_PATH.read_text())["mode"] == "check"


def test_target_is_frozen_abs2_with_max_margin_utilization(monkeypatch):
    import scripts.propr_competition as competition

    signals = pd.Series({
        "BTC": 0.1, "ETH": 0.2, "SOL": -0.1,
        "XRP": -0.2, "SUI": 0.3, "NEAR": -0.3,
    })
    prices = {asset: 100.0 for asset in competition.SYMBOLS}
    monkeypatch.setattr(competition, "trailing_returns", lambda *_args: (signals, prices))

    target, observed_prices = competition._target(50_000)

    assert set(target) == {"SUI", "NEAR"}
    assert target == {"SUI": 47_500.0, "NEAR": -47_500.0}
    assert sum(
        abs(value) / competition.MAX_LEVERAGE_BY_ASSET[asset]
        for asset, value in target.items()
    ) == pytest.approx(47_500)
    assert competition.GROSS * float(competition.STOP_DISTANCE) <= competition.DAILY_STOP_PCT
    assert target["SUI"] > 0 and target["NEAR"] < 0
    assert observed_prices == prices


def test_btc_eth_abs2_uses_their_full_five_x_caps(monkeypatch):
    import scripts.propr_competition as competition

    signals = pd.Series({
        "BTC": 0.6, "ETH": -0.5, "SOL": 0.1,
        "XRP": -0.2, "SUI": 0.3, "NEAR": -0.3,
    })
    prices = {asset: 100.0 for asset in competition.SYMBOLS}
    monkeypatch.setattr(competition, "trailing_returns", lambda *_args: (signals, prices))

    target, _observed_prices = competition._target(50_000)

    assert target == {"BTC": 118_750.0, "ETH": -118_750.0}
    assert sum(abs(value) for value in target.values()) == pytest.approx(237_500)


def test_guard_flattens_at_end_even_when_automanage_is_off(tmp_path, monkeypatch):
    import scripts.propr_competition as competition

    events = []

    class Client:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()
            self.positions = [_position()]

        def setup(self, **kwargs):
            assert kwargs == {
                "expected_account_id": "competition-1",
                "expected_competition_id": competition.COMPETITION_ID,
                "expected_competition_slug": competition.COMPETITION_SLUG,
            }

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
            assert kwargs == {
                "expected_account_id": "competition-1",
                "expected_competition_id": competition.COMPETITION_ID,
                "expected_competition_slug": competition.COMPETITION_SLUG,
            }

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
    monkeypatch.setattr(competition, "_ensure_leverage", lambda *_args: None)
    monkeypatch.setattr(competition, "rebalance", fake_rebalance)
    monkeypatch.setattr(competition, "_flatten_and_cleanup", fake_flatten_cleanup)
    monkeypatch.setattr(
        competition,
        "_target",
        lambda *_args: ({"BTC": 100.0, "ETH": -100.0}, {"BTC": 100.0, "ETH": 100.0}),
    )
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
    monkeypatch.setattr(competition, "_ensure_leverage", lambda *_args: None)
    monkeypatch.setattr(competition, "rebalance", fake_rebalance)
    monkeypatch.setattr(
        competition, "_append_journal",
        lambda *_args: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(competition, "_flatten_and_cleanup", fake_flatten)
    monkeypatch.setattr(
        competition,
        "_target",
        lambda *_args: ({"BTC": 100.0, "ETH": -100.0}, {"BTC": 100.0, "ETH": 100.0}),
    )
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
    monkeypatch.setattr(
        competition,
        "_target",
        lambda *_args: (
            {"BTC": float("nan"), "ETH": -100.0},
            {"BTC": 100.0, "ETH": 100.0},
        ),
    )
    monkeypatch.setattr(
        competition,
        "rebalance",
        lambda *_args: pytest.fail("non-finite target reached order path"),
    )
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")

    with pytest.raises(competition.ProprError, match="target_recovery"):
        competition.manage()

    assert events == [("flatten", "target_recovery", 0)]


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
    monkeypatch.setattr(competition, "JOURNAL_PATH", tmp_path / "journal.jsonl")
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

    position = _position(mark="91", entry="100", notional="91")
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


def test_legacy_state_migration_preserves_risk_and_forces_rebalance():
    import scripts.propr_competition as competition

    state = _state(
        competition,
        datetime(2026, 7, 23, 18, 38, tzinfo=timezone.utc),
        strategy=competition.LEGACY_STRATEGY_ID,
        day_start_equity=49_900,
        high_water_mark=50_120,
        last_equity=50_050,
        last_rebalance_ts="2026-07-23T18:39:00+00:00",
    )

    migrated = competition._migrate_state(state)

    assert state["strategy"] == competition.LEGACY_STRATEGY_ID
    assert migrated["strategy"] == competition.STRATEGY_ID
    assert migrated["day_start_equity"] == 49_900
    assert migrated["high_water_mark"] == 50_120
    assert migrated["last_equity"] == 50_050
    assert migrated["migration"]["forced_rebalance"] is True
    assert competition._due(
        migrated,
        datetime(2026, 7, 23, 19, 5, tzinfo=timezone.utc),
    ) is True


def test_unknown_strategy_state_is_rejected():
    import scripts.propr_competition as competition

    state = _state(
        competition,
        datetime(2026, 7, 23, 18, 38, tzinfo=timezone.utc),
        strategy="unknown",
    )

    with pytest.raises(competition.ProprError, match="strategy"):
        competition._validate_state(state, "competition-1")


def test_runtime_accepts_exact_legacy_stop_during_migration():
    import scripts.propr_competition as competition

    position = _position()
    plan = competition._stop_plan(position, legacy=True)
    order = {
        "orderId": "legacy-stop",
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
    state = _state(
        competition,
        datetime(2026, 7, 23, 18, 38, tzinfo=timezone.utc),
        strategy=competition.LEGACY_STRATEGY_ID,
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
        expected_quantities={"BTC": "1"},
        last_target={"BTC": 100.0},
        last_rebalance_ts="2026-07-23T18:39:00+00:00",
    )

    assert competition._runtime_book_errors(state, [position], [order]) == []
    assert competition._is_exact_protection(position, order) is False


@pytest.mark.parametrize("entrypoint", ["guard", "manage"])
def test_legacy_drift_is_blocked_before_migration_or_normal_stop_writes(
    tmp_path,
    monkeypatch,
    entrypoint,
):
    import scripts.propr_competition as competition

    position = _position()

    class Client:
        def __init__(self, *, read_only=False):
            assert read_only is False
            self.active_attempt = _attempt()

        def setup(self, **_kwargs):
            return None

        def get_positions(self):
            return [position]

        def get_account(self):
            return _account()

        def get_active_orders(self):
            return []

        def create_order(self, **_kwargs):
            pytest.fail("legacy drift reached stop creation")

        def cancel_order(self, _order_id):
            pytest.fail("legacy drift reached stop cancellation")

    def fake_recovery(_client, state, _now, reason, error):
        assert state["strategy"] == competition.LEGACY_STRATEGY_ID
        assert reason == "legacy_migration_preflight"
        assert "BTC:stop_count=0" in str(error)
        raise competition.ProprError(reason)

    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_AUTOMANAGE_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 23, 19, 20, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(competition, "ProprClient", Client)
    monkeypatch.setattr(competition, "_recover_after_write", fake_recovery)
    monkeypatch.setattr(
        competition,
        "_migrate_state",
        lambda _state: pytest.fail("legacy drift reached migration"),
    )
    monkeypatch.setattr(
        competition,
        "_create_missing_stops",
        lambda *_args: pytest.fail("legacy drift reached normal stop path"),
    )
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")
    state = _state(
        competition,
        datetime(2026, 7, 23, 18, 38, tzinfo=timezone.utc),
        strategy=competition.LEGACY_STRATEGY_ID,
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
        expected_quantities={"BTC": "1"},
        last_target={"BTC": 100.0},
        last_rebalance_ts="2026-07-23T18:39:00+00:00",
    )
    competition.STATE_PATH.write_text(json.dumps(state))

    with pytest.raises(competition.ProprError, match="legacy_migration_preflight"):
        getattr(competition, entrypoint)()


def test_stop_replacement_creates_before_cancelling_legacy(
    tmp_path,
    monkeypatch,
):
    import scripts.propr_competition as competition

    position = _position()
    legacy_plan = competition._stop_plan(position, legacy=True)
    old_order = {
        "orderId": "legacy-stop",
        "intentId": legacy_plan["intent_id"],
        "positionId": legacy_plan["position_id"],
        "type": "stop_market",
        "side": legacy_plan["side"],
        "positionSide": legacy_plan["position_side"],
        "quantity": legacy_plan["quantity"],
        "triggerPrice": legacy_plan["trigger_price"],
        "reduceOnly": True,
        "closePosition": True,
    }

    class Client:
        def __init__(self):
            self.orders = [old_order]
            self.events = []

        def get_active_orders(self):
            return list(self.orders)

        def create_order(self, **kwargs):
            self.events.append("create")
            order = {
                "orderId": "new-stop",
                "status": "pending",
                "type": kwargs["order_type"],
                "asset": kwargs["asset"],
                "side": kwargs["side"],
                "positionSide": kwargs["position_side"],
                "quantity": kwargs["quantity"],
                "triggerPrice": kwargs["trigger_price"],
                "intentId": kwargs["intent_id"],
                "positionId": kwargs["position_id"],
                "reduceOnly": kwargs["reduce_only"],
                "closePosition": kwargs["close_position"],
            }
            self.orders.append(order)
            return [order]

        def cancel_order(self, order_id):
            self.events.append("cancel")
            self.orders = [order for order in self.orders if order["orderId"] != order_id]
            return {"orderId": order_id, "status": "cancelled"}

    client = Client()
    monkeypatch.setattr(competition, "JOURNAL_PATH", tmp_path / "journal.jsonl")

    competition._create_missing_stops(client, [position])

    assert client.events == ["create", "cancel"]
    assert [order["orderId"] for order in client.orders] == ["new-stop"]


def test_stop_create_failure_keeps_legacy_stop():
    import scripts.propr_competition as competition

    position = _position()
    legacy_plan = competition._stop_plan(position, legacy=True)
    old_order = {
        "orderId": "legacy-stop",
        "intentId": legacy_plan["intent_id"],
        "positionId": legacy_plan["position_id"],
        "type": "stop_market",
        "side": legacy_plan["side"],
        "positionSide": legacy_plan["position_side"],
        "quantity": legacy_plan["quantity"],
        "triggerPrice": legacy_plan["trigger_price"],
        "reduceOnly": True,
        "closePosition": True,
    }

    class Client:
        def get_active_orders(self):
            return [old_order]

        def create_order(self, **_kwargs):
            raise competition.ProprError("create failed")

        def cancel_order(self, _order_id):
            pytest.fail("legacy stop cancelled after create failure")

    with pytest.raises(competition.ProprError, match="create failed"):
        competition._create_missing_stops(Client(), [position])


def test_leverage_is_updated_and_read_back_before_trading(tmp_path, monkeypatch):
    import scripts.propr_competition as competition

    class Client:
        def __init__(self):
            self.configs = {
                asset: {
                    "configId": f"cfg-{asset}",
                    "asset": asset,
                    "leverage": 1,
                    "marginMode": "cross",
                }
                for asset in ("NEAR", "SUI")
            }
            self.events = []

        def get_leverage_limits(self):
            self.events.append("limits")
            return {"defaults": {"crypto": 2}, "overrides": {"BTC": 5, "ETH": 5}}

        def get_margin_config(self, asset):
            self.events.append(f"get:{asset}")
            return dict(self.configs[asset])

        def update_margin_config(self, config_id, asset, leverage, margin_mode="cross"):
            self.events.append(f"put:{asset}")
            assert config_id == f"cfg-{asset}"
            self.configs[asset].update(leverage=leverage, marginMode=margin_mode)
            return dict(self.configs[asset])

    client = Client()
    monkeypatch.setattr(competition, "JOURNAL_PATH", tmp_path / "journal.jsonl")

    competition._ensure_leverage(client, ["SUI", "NEAR"])

    assert client.configs["NEAR"]["leverage"] == competition.MAX_LEVERAGE_BY_ASSET["NEAR"]
    assert client.configs["SUI"]["leverage"] == competition.MAX_LEVERAGE_BY_ASSET["SUI"]
    assert client.events.index("put:NEAR") > client.events.index("get:SUI")
    assert client.events[-2:] == ["get:NEAR", "get:SUI"]


def test_leverage_update_detection_is_read_only():
    import scripts.propr_competition as competition

    class Client:
        def __init__(self):
            self.events = []

        def get_leverage_limits(self):
            self.events.append("limits")
            return {"defaults": {"crypto": 2}}

        def get_margin_config(self, asset):
            self.events.append(f"get:{asset}")
            return {
                "configId": f"cfg-{asset}",
                "asset": asset,
                "leverage": (
                    1 if asset == "NEAR"
                    else competition.MAX_LEVERAGE_BY_ASSET[asset]
                ),
                "marginMode": "cross",
            }

        def update_margin_config(self, *_args, **_kwargs):
            pytest.fail("read-only leverage inspection attempted a write")

    client = Client()

    assert competition._leverage_needs_update(client, ["XRP", "NEAR"]) is True
    assert client.events == ["limits", "get:NEAR", "get:XRP"]


def test_global_leverage_detection_sees_alt_mismatch_when_btc_eth_are_maxed():
    import scripts.propr_competition as competition

    class Client:
        def get_leverage_limits(self):
            return {
                "defaults": {"crypto": 2},
                "overrides": {"BTC": 5, "ETH": 5},
            }

        def get_margin_config(self, asset):
            leverage = competition.MAX_LEVERAGE_BY_ASSET[asset]
            if asset == "SOL":
                leverage = 1
            return {
                "configId": f"cfg-{asset}",
                "asset": asset,
                "leverage": leverage,
                "marginMode": "cross",
            }

    client = Client()

    assert competition._leverage_needs_update(client, ["BTC", "ETH"]) is False
    assert competition._leverage_needs_update(
        client,
        list(competition.SYMBOLS),
    ) is True


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (
            {"configId": "cfg-BTC", "leverage": 5, "marginMode": "cross"},
            "asset inatteso",
        ),
        (
            {"asset": "BTC", "leverage": 5, "marginMode": "cross"},
            "configId.*assente",
        ),
        (
            {"configId": "cfg-BTC", "asset": "BTC", "leverage": 5},
            "margin mode.*assente",
        ),
    ],
)
def test_margin_config_contract_rejects_missing_identity_fields(config, message):
    import scripts.propr_competition as competition

    with pytest.raises(competition.ProprError, match=message):
        competition._margin_config_matches(config, "BTC", 5)


def test_manage_persists_marker_then_migrates_and_is_idempotent(
    tmp_path,
    monkeypatch,
):
    import scripts.propr_competition as competition

    events = []

    class Client:
        def __init__(self):
            self.active_attempt = _attempt()
            self.positions = [_position()]
            self.orders = []

        def setup(self, **_kwargs):
            return None

        def get_positions(self):
            return list(self.positions)

        def get_account(self):
            return _account()

        def get_active_orders(self):
            return list(self.orders)

    client = Client()

    def fake_guard(active_client, positions):
        events.append(("guard", [position["base"] for position in positions]))
        active_client.orders = []
        for position in positions:
            plan = competition._stop_plan(position)
            active_client.orders.append({
                "orderId": f"stop-{position['base']}",
                "intentId": plan["intent_id"],
                "positionId": plan["position_id"],
                "type": "stop_market",
                "side": plan["side"],
                "positionSide": plan["position_side"],
                "quantity": plan["quantity"],
                "triggerPrice": plan["trigger_price"],
                "reduceOnly": True,
                "closePosition": True,
            })
        return []

    def fake_flatten(active_client, positions, reason):
        events.append(("flatten", reason, [position["base"] for position in positions]))
        active_client.positions = []
        active_client.orders = []

    def fake_rebalance(active_client, _target, _prices, positions):
        assert positions == []
        events.append(("rebalance",))
        active_client.positions = [
            _position("NEAR", "short", quantity="475", notional="47500"),
            _position("XRP", "long", quantity="475", notional="47500"),
        ]
        return [
            {
                "asset": "NEAR",
                "action": "adjust",
                "resp": [{"orderId": "near", "status": "filled"}],
            },
            {
                "asset": "XRP",
                "action": "adjust",
                "resp": [{"orderId": "xrp", "status": "filled"}],
            },
        ]

    monkeypatch.setenv("PROPR_COMPETITION_AUTOMANAGE_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 23, 19, 30, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        competition,
        "ProprClient",
        lambda *, read_only=False: client
        if read_only is False
        else pytest.fail("manage requested read-only client"),
    )
    monkeypatch.setattr(competition, "_create_missing_stops", fake_guard)
    def fake_needs_update(_client, assets):
        assert assets == list(competition.SYMBOLS)
        events.append(("inspect_leverage",))
        return True

    monkeypatch.setattr(competition, "_leverage_needs_update", fake_needs_update)
    monkeypatch.setattr(
        competition,
        "_ensure_leverage",
        lambda _client, assets: events.append(("set_leverage", tuple(assets))),
    )
    monkeypatch.setattr(competition, "_flatten_and_cleanup", fake_flatten)
    monkeypatch.setattr(competition, "rebalance", fake_rebalance)
    monkeypatch.setattr(
        competition,
        "_target",
        lambda *_args: (
            {"NEAR": -47_500.0, "XRP": 47_500.0},
            {"NEAR": 100.0, "XRP": 100.0},
        ),
    )
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(competition, "JOURNAL_PATH", tmp_path / "journal.jsonl")
    state = _state(
        competition,
        datetime(2026, 7, 23, 18, 38, tzinfo=timezone.utc),
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
        expected_quantities={"BTC": "1"},
        last_target={"BTC": 100.0},
        last_rebalance_ts="2026-07-23T01:00:00+00:00",
    )
    competition.STATE_PATH.write_text(json.dumps(state))

    prepared = competition.manage()

    assert prepared["action"] == competition.LEVERAGE_MIGRATION_PHASE
    assert prepared["positions"] == 1
    prepared_state = json.loads(competition.STATE_PATH.read_text())
    assert prepared_state["expected_assets"] == ["BTC"]
    assert prepared_state["migration"]["phase"] == competition.LEVERAGE_MIGRATION_PHASE
    assert prepared_state["migration"]["pending_target"] == {
        "NEAR": -47_500.0,
        "XRP": 47_500.0,
    }
    assert events == [
        ("guard", ["BTC"]),
        ("inspect_leverage",),
    ]

    migrated = competition.manage()

    assert migrated["action"] == "rebalance"
    assert migrated["positions"] == 2
    assert events == [
        ("guard", ["BTC"]),
        ("inspect_leverage",),
        ("guard", ["BTC"]),
        ("flatten", "leverage_migration", ["BTC"]),
        ("set_leverage", tuple(competition.SYMBOLS)),
        ("rebalance",),
        ("guard", ["NEAR", "XRP"]),
    ]
    saved = json.loads(competition.STATE_PATH.read_text())
    assert saved["expected_assets"] == ["NEAR", "XRP"]
    assert saved["permanently_halted"] is False
    assert saved["migration"]["phase"] == "complete"
    assert saved["migration"]["forced_rebalance"] is False

    third = competition.manage()

    assert third["action"] == "guard_only"
    assert events[-1] == ("guard", ["NEAR", "XRP"])


def test_pending_migration_resumes_from_remote_old_state_and_live_flat(
    tmp_path,
    monkeypatch,
):
    import scripts.propr_competition as competition

    class Client:
        def __init__(self):
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

    client = Client()
    leverage_attempts = 0

    def fake_leverage(_client, assets):
        nonlocal leverage_attempts
        leverage_attempts += 1
        assert assets == list(competition.SYMBOLS)
        if leverage_attempts == 1:
            raise competition.ProprError("update failed after partial PUT")

    def fake_rebalance(active_client, _target, _prices, positions):
        assert positions == []
        active_client.positions = [
            _position("NEAR", "short", quantity="475", notional="47500"),
            _position("XRP", "long", quantity="475", notional="47500"),
        ]
        return [
            {
                "asset": "NEAR",
                "action": "adjust",
                "resp": [{"orderId": "near", "status": "filled"}],
            },
            {
                "asset": "XRP",
                "action": "adjust",
                "resp": [{"orderId": "xrp", "status": "filled"}],
            },
        ]

    monkeypatch.setenv("PROPR_COMPETITION_AUTOMANAGE_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_GUARD_ENABLED", "true")
    monkeypatch.setenv("PROPR_COMPETITION_ACCOUNT_ID", "competition-1")
    monkeypatch.setattr(
        competition, "_now",
        lambda: datetime(2026, 7, 23, 19, 30, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        competition,
        "ProprClient",
        lambda *, read_only=False: client
        if read_only is False
        else pytest.fail("manage requested read-only client"),
    )
    monkeypatch.setattr(competition, "_create_missing_stops", lambda *_args: [])
    monkeypatch.setattr(competition, "_ensure_leverage", fake_leverage)
    monkeypatch.setattr(competition, "rebalance", fake_rebalance)
    monkeypatch.setattr(
        competition,
        "_target",
        lambda *_args: pytest.fail("pending migration recomputed target"),
    )
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(competition, "JOURNAL_PATH", tmp_path / "journal.jsonl")
    state = _state(
        competition,
        datetime(2026, 7, 23, 18, 38, tzinfo=timezone.utc),
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
        expected_quantities={"BTC": "1"},
        last_target={"BTC": 100.0},
        last_rebalance_ts="2026-07-23T01:00:00+00:00",
        migration={
            "phase": competition.LEVERAGE_MIGRATION_PHASE,
            "pending_target": {"NEAR": -47_500.0, "XRP": 47_500.0},
            "pending_prices": {"NEAR": 100.0, "XRP": 100.0},
            "forced_rebalance": True,
        },
    )
    competition.STATE_PATH.write_text(json.dumps(state))

    with pytest.raises(competition.ProprError, match="leverage_preflight"):
        competition.manage()

    saved = json.loads(competition.STATE_PATH.read_text())
    assert saved["expected_assets"] == []
    assert saved["expected_sides"] == {}
    assert saved["expected_quantities"] == {}
    assert saved["last_target"] == {}
    assert saved["permanently_halted"] is False
    assert saved["migration"]["phase"] == competition.LEVERAGE_MIGRATION_PHASE

    resumed = competition.manage()

    assert resumed["action"] == "rebalance"
    assert resumed["positions"] == 2
    assert leverage_attempts == 2
    completed = json.loads(competition.STATE_PATH.read_text())
    assert completed["expected_assets"] == ["NEAR", "XRP"]
    assert completed["migration"]["phase"] == "complete"

    assert competition.manage()["action"] == "guard_only"


def test_check_accepts_pending_migration_after_crash_left_account_flat(
    tmp_path,
    monkeypatch,
):
    import scripts.propr_competition as competition

    class ReadOnlyClient:
        def __init__(self, *, read_only=False):
            assert read_only is True
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
    monkeypatch.setattr(competition, "ProprClient", ReadOnlyClient)
    monkeypatch.setattr(competition, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(competition, "STATUS_PATH", tmp_path / "status.json")
    state = _state(
        competition,
        datetime(2026, 7, 23, 18, 38, tzinfo=timezone.utc),
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
        expected_quantities={"BTC": "1"},
        last_target={"BTC": 100.0},
        last_rebalance_ts="2026-07-23T01:00:00+00:00",
        migration={
            "phase": competition.LEVERAGE_MIGRATION_PHASE,
            "pending_target": {"NEAR": -47_500.0, "XRP": 47_500.0},
            "pending_prices": {"NEAR": 100.0, "XRP": 100.0},
        },
    )
    competition.STATE_PATH.write_text(json.dumps(state))

    result = competition.check()

    assert result["positions"] == 0
    assert result["writes"] == 0


def test_pending_migration_accepts_only_protected_reduction_subset():
    import scripts.propr_competition as competition

    state = _state(
        competition,
        datetime(2026, 7, 23, 18, 38, tzinfo=timezone.utc),
        expected_assets=["BTC"],
        expected_sides={"BTC": "long"},
        expected_quantities={"BTC": "1"},
        last_target={"BTC": 100.0},
        last_rebalance_ts="2026-07-23T01:00:00+00:00",
        migration={"phase": competition.LEVERAGE_MIGRATION_PHASE},
    )
    residual = _position(quantity="0.5", notional="50")
    plan = competition._stop_plan(residual)
    stop = {
        "orderId": "residual-stop",
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

    assert competition._active_runtime_errors(state, [residual], [stop]) == []
    assert "BTC:oversize" in competition._active_runtime_errors(
        state,
        [_position(quantity="1.1", notional="110")],
        [],
    )


def test_leverage_cap_failure_happens_before_config_write():
    import scripts.propr_competition as competition

    class Client:
        def __init__(self):
            self.updated = False

        def get_leverage_limits(self):
            return {"defaults": {"crypto": 1}}

        def get_margin_config(self, _asset):
            pytest.fail("config read reached after leverage cap failure")

        def update_margin_config(self, *_args, **_kwargs):
            self.updated = True

    client = Client()
    with pytest.raises(competition.ProprError, match="inattesa"):
        competition._ensure_leverage(client, ["SUI"])
    assert client.updated is False


def test_workflow_keeps_competition_dormant_by_default():
    workflow = (ROOT / ".github/workflows/propr-competition.yml").read_text()

    sync_index = workflow.index("git pull --ff-only origin main")
    check_index = workflow.index("uv run scripts/propr_competition.py --check")
    assert "ref: main" in workflow
    assert "fetch-depth: 0" in workflow
    assert sync_index < check_index
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
