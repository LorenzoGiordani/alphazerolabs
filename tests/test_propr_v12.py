import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import propr_v12  # noqa: E402
from scripts.propr_client import ProprError  # noqa: E402
from scripts.propr_turbo_risk import DailySnapshot, RiskMemory  # noqa: E402


ACCOUNT_ID = "turbo-10k-dedicated"
CHALLENGE_SLUG = "explorer-turbo"
STATE_HMAC_KEY = "test-only-v12-state-hmac-key-32-bytes-minimum"
SOURCE_FREEZE_SHA256 = "a" * 64
CHECKER_RECEIPT_SHA256 = "b" * 64
NOW = datetime(2026, 7, 23, 12, tzinfo=timezone.utc)
MIDNIGHT = datetime(2026, 7, 23, tzinfo=timezone.utc)


def _attempt(*, account_id=ACCOUNT_ID, name="Explorer 1-Step Turbo", slug=CHALLENGE_SLUG):
    return {
        "accountId": account_id,
        "status": "active",
        "challenge": {
            "name": name,
            "slug": slug,
            "initialBalance": "10000",
            "drawdownType": "static",
            "phases": [
                {
                    "profitTargetPercent": "9",
                    "maxDailyLossPercent": "3",
                    "maxDrawdownPercent": "3",
                }
            ],
        },
    }


def _account(*, balance="10000", unrealized="0", isolated="0"):
    return {
        "balance": balance,
        "totalUnrealizedPnl": unrealized,
        "isolatedPositionMargin": isolated,
    }


def _position(
    *,
    asset="BTC",
    side="long",
    quantity="0.01",
    notional="1000",
    mark="100000",
    margin_mode="cross",
):
    return {
        "positionId": f"position-{asset}",
        "base": asset,
        "positionSide": side,
        "quantity": quantity,
        "notionalValue": notional,
        "markPrice": mark,
        "marginMode": margin_mode,
    }


def _order(order_id="order-1"):
    return {"orderId": order_id, "status": "open"}


class FakeClient:
    def __init__(
        self,
        *,
        read_only,
        account=None,
        positions=None,
        orders=None,
        attempt=None,
        clear_on_flatten=True,
    ):
        self.read_only = read_only
        self.account = account or _account()
        self.positions = list(positions or [])
        self.orders = list(orders or [])
        self.active_attempt = attempt or _attempt()
        self.clear_on_flatten = clear_on_flatten
        self.created = []
        self.cancelled = []

    def setup(self, **kwargs):
        assert kwargs == {
            "expected_account_id": ACCOUNT_ID,
            "expected_challenge_slug": CHALLENGE_SLUG,
        }

    def get_account(self):
        return dict(self.account)

    def get_positions(self):
        return list(self.positions)

    def get_active_orders(self):
        return list(self.orders)

    def cancel_order(self, order_id):
        if self.read_only:
            raise AssertionError("read-only client cancelled an order")
        self.cancelled.append(order_id)
        self.orders = [item for item in self.orders if item["orderId"] != order_id]
        return {"orderId": order_id, "status": "cancelled"}

    def create_order(self, **kwargs):
        if self.read_only:
            raise AssertionError("read-only client created an order")
        assert kwargs["reduce_only"] is True
        assert kwargs["close_position"] is True
        assert kwargs["position_side"] in ("long", "short")
        self.created.append(kwargs)
        if self.clear_on_flatten:
            self.positions = []
        return [{"orderId": "flatten-1", "status": "filled"}]


def _factory(client):
    def build(*, read_only):
        assert read_only is client.read_only
        return client

    return build


def _set_env(monkeypatch, tmp_path, *, manage=False, guard=False):
    monkeypatch.setenv("PROPR_V12_ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.setenv("PROPR_V12_CHALLENGE_SLUG", CHALLENGE_SLUG)
    monkeypatch.setenv("PROPR_V12_API_KEY", "pk_test_never_used")
    monkeypatch.setenv("PROPR_V12_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("PROPR_V12_STATE_HMAC_KEY", STATE_HMAC_KEY)
    monkeypatch.setenv("PROPR_V12_SOURCE_FREEZE_SHA256", SOURCE_FREEZE_SHA256)
    monkeypatch.setenv(
        "PROPR_V12_CHECKER_RECEIPT_SHA256",
        CHECKER_RECEIPT_SHA256,
    )
    monkeypatch.setenv("PROPR_V12_AUTOMANAGE_ENABLED", str(manage).lower())
    monkeypatch.setenv("PROPR_V12_GUARD_ENABLED", str(guard).lower())


def _write_state(tmp_path, *, snapshot_at=MIDNIGHT, memory=None):
    path = tmp_path / "state.json"
    propr_v12._write_state(
        path,
        DailySnapshot(
            account_id=ACCOUNT_ID,
            as_of_utc=snapshot_at,
            day_start_realized_balance=Decimal("10000"),
            day_start_equity=Decimal("10000"),
        ),
        memory or RiskMemory(account_id=ACCOUNT_ID),
    )
    return path


def _valid_target(tmp_path, *, created_at=NOW):
    path = tmp_path / "target.json"
    weights = {symbol: "0" for symbol in propr_v12.CORE_SYMBOLS}
    weights["BTC"] = str(Decimal(1) / Decimal(30))
    weights["ETH"] = str(-(Decimal(1) / Decimal(30)))
    monday = datetime(2026, 7, 20, tzinfo=timezone.utc)
    payload = {
        "schema_version": 1,
        "strategy_id": propr_v12.STRATEGY_ID,
        "account_id": ACCOUNT_ID,
        "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
        "weekly_anchor_ms": int(monday.timestamp() * 1000),
        "source_freeze_sha256": SOURCE_FREEZE_SHA256,
        "checker_receipt_sha256": CHECKER_RECEIPT_SHA256,
        "weights": weights,
    }
    path.write_text(json.dumps(payload))
    return path


def test_attempt_validation_requires_exact_turbo_rules_and_pin():
    propr_v12._validate_attempt(_attempt(), ACCOUNT_ID, CHALLENGE_SLUG)

    bad = (
        _attempt(account_id="other"),
        _attempt(name="Free Trial", slug="free-trial"),
        _attempt(slug="different-turbo"),
        {
            **_attempt(),
            "challenge": {
                **_attempt()["challenge"],
                "phases": [
                    {
                        "profitTargetPercent": "10",
                        "maxDailyLossPercent": "3",
                        "maxDrawdownPercent": "3",
                    }
                ],
            },
        },
    )
    for attempt in bad:
        with pytest.raises(ProprError):
            propr_v12._validate_attempt(attempt, ACCOUNT_ID, CHALLENGE_SLUG)


def test_check_missing_pristine_state_is_read_only(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path)
    client = FakeClient(read_only=True)

    result = propr_v12.check(now=NOW, client_factory=_factory(client))

    assert result == {
        "mode": "check",
        "ready": False,
        "production_ready": False,
        "reason": "pristine_state_initialization_required",
        "writes": 0,
        "account_id": ACCOUNT_ID,
        "positions": 0,
        "active_orders": 0,
    }
    assert not (tmp_path / "state.json").exists()
    assert client.created == []
    assert client.cancelled == []


def test_check_existing_state_evaluates_without_writes(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path)
    path = _write_state(tmp_path)
    before = path.read_bytes()
    client = FakeClient(read_only=True)

    result = propr_v12.check(now=NOW, client_factory=_factory(client))

    assert result["mode"] == "check"
    assert result["ready"] is False
    assert result["risk_gate_ready"] is True
    assert result["production_ready"] is False
    assert result["production_blocker"] == (
        "realtime_websocket_watchdog_and_entry_executor_missing"
    )
    assert result["writes"] == 0
    assert result["decision"]["reason"] == "risk_budget_available"
    assert path.read_bytes() == before


def test_manage_is_disabled_before_client_or_credentials(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path, manage=False, guard=False)

    result = propr_v12.manage(
        now=NOW,
        client_factory=lambda **_kwargs: pytest.fail("client reached"),
    )

    assert result == {"mode": "disabled", "production_ready": False, "writes": 0}


def test_manage_requires_independent_guard_switch(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path, manage=True, guard=False)

    with pytest.raises(ProprError, match="GUARD"):
        propr_v12.manage(
            now=NOW,
            client_factory=lambda **_kwargs: pytest.fail("client reached"),
        )


def test_manage_initialises_only_pristine_account_and_never_enters_without_target(
    tmp_path,
    monkeypatch,
):
    _set_env(monkeypatch, tmp_path, manage=True, guard=True)
    client = FakeClient(read_only=False)

    result = propr_v12.manage(now=NOW, client_factory=_factory(client))

    assert result["mode"] == "armed_no_target"
    assert result["production_ready"] is False
    assert result["orders_created"] == 0
    assert result["decision"]["state"] == "ACTIVE"
    assert client.created == []
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["account_id"] == ACCOUNT_ID
    assert state["risk_memory"]["state"] == "ACTIVE"
    assert state["snapshot"]["as_of_utc"] == "2026-07-23T00:00:00Z"
    assert len(state["hmac_sha256"]) == 64


def test_manage_refuses_non_pristine_first_activation(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path, manage=True, guard=True)
    client = FakeClient(read_only=False, positions=[_position()])

    with pytest.raises(ProprError, match="non pristine"):
        propr_v12.manage(now=NOW, client_factory=_factory(client))

    assert not (tmp_path / "state.json").exists()
    assert client.created == []


def test_soft_trigger_writes_lock_before_cancel_flatten_and_confirms_empty(
    tmp_path,
    monkeypatch,
):
    _set_env(monkeypatch, tmp_path, manage=True, guard=True)
    _write_state(tmp_path)
    monkeypatch.setattr(propr_v12.time, "sleep", lambda _seconds: None)
    client = FakeClient(
        read_only=False,
        account=_account(balance="10000", unrealized="-201"),
        positions=[_position()],
        orders=[_order()],
    )

    result = propr_v12.manage(now=NOW, client_factory=_factory(client))

    assert result["mode"] == "flat_guarded"
    assert result["production_ready"] is False
    assert result["reason"] == "soft_floor_touch"
    assert result["actions"] == {"cancelled": 1, "flatten_orders": 1}
    assert len(client.created) == 1
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["risk_memory"] == {
        "account_id": ACCOUNT_ID,
        "locked_utc_date": "2026-07-23",
        "state": "LOCKED_TODAY",
    }


def test_failed_flat_readback_keeps_persisted_lock(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path, manage=True, guard=True)
    _write_state(tmp_path)
    monkeypatch.setattr(propr_v12.time, "sleep", lambda _seconds: None)
    client = FakeClient(
        read_only=False,
        account=_account(balance="10000", unrealized="-201"),
        positions=[_position()],
        clear_on_flatten=False,
    )

    with pytest.raises(ProprError, match="non confermato"):
        propr_v12.manage(now=NOW, client_factory=_factory(client))

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["risk_memory"]["state"] == "LOCKED_TODAY"
    assert len(client.created) == propr_v12.RECOVERY_ATTEMPTS


def test_missed_midnight_with_exposure_locks_and_flattens(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path, manage=True, guard=True)
    _write_state(tmp_path, snapshot_at=MIDNIGHT - timedelta(days=1))
    monkeypatch.setattr(propr_v12.time, "sleep", lambda _seconds: None)
    client = FakeClient(read_only=False, positions=[_position()])

    result = propr_v12.manage(now=NOW, client_factory=_factory(client))

    assert result["mode"] == "locked"
    assert result["production_ready"] is False
    assert result["reason"] == "missed_00utc_snapshot"
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["risk_memory"]["state"] == "LOCKED_TODAY"
    assert client.positions == []


def test_positions_fail_closed_on_wrong_asset_or_margin_mode():
    with pytest.raises(ProprError, match="asset"):
        propr_v12._validate_positions([_position(asset="DOGE")])
    with pytest.raises(ProprError, match="cross"):
        propr_v12._validate_positions([_position(margin_mode="isolated")])


def test_target_contract_is_bounded_and_manage_still_has_no_entry_executor(
    tmp_path,
    monkeypatch,
):
    _set_env(monkeypatch, tmp_path, manage=True, guard=True)
    _write_state(tmp_path)
    target = _valid_target(tmp_path)
    monkeypatch.setenv("PROPR_V12_TARGET_PATH", str(target))
    client = FakeClient(read_only=False)

    result = propr_v12.manage(now=NOW, client_factory=_factory(client))

    assert result["mode"] == "target_validated_execution_disabled"
    assert result["production_ready"] is False
    assert result["target_nonzero_weights"] == 2
    assert result["orders_created"] == 0
    assert client.created == []


def test_stale_or_overgross_target_fails_closed(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path)
    stale = _valid_target(tmp_path, created_at=NOW - timedelta(minutes=16))
    with pytest.raises(ProprError, match="stale"):
        propr_v12._target_contract(stale, account_id=ACCOUNT_ID, now=NOW)

    current = _valid_target(tmp_path, created_at=NOW)
    payload = json.loads(current.read_text())
    payload["weights"]["BTC"] = "0.04"
    current.write_text(json.dumps(payload))
    with pytest.raises(ProprError, match="cap per-asset"):
        propr_v12._target_contract(current, account_id=ACCOUNT_ID, now=NOW)


def test_numeric_trust_boundaries_reject_float_nan_and_isolated_margin():
    with pytest.raises(ProprError):
        propr_v12._decimal(1.0, "float")
    with pytest.raises(ProprError):
        propr_v12._decimal("NaN", "nan")
    with pytest.raises(ProprError, match="isolato"):
        propr_v12._account_values(_account(isolated="1"))


def test_account_provider_equity_cross_check_fails_closed():
    matching = {**_account(unrealized="-12"), "equity": "9988", "marginBalance": "9988"}
    assert propr_v12._account_values(matching) == (
        Decimal("10000"),
        Decimal("9988"),
    )

    for field in ("equity", "marginBalance"):
        mismatched = {**matching, field: "9988.01"}
        with pytest.raises(ProprError, match=field):
            propr_v12._account_values(mismatched)


def test_state_hmac_detects_coherent_payload_tampering(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path)
    path = _write_state(tmp_path)
    payload = json.loads(path.read_text())
    payload["snapshot"]["day_start_equity"] = "20000"
    path.write_text(json.dumps(payload))

    with pytest.raises(ProprError, match="HMAC"):
        propr_v12._read_state(path, ACCOUNT_ID)


def test_missed_midnight_locks_even_when_account_is_flat(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path, manage=True, guard=True)
    _write_state(tmp_path, snapshot_at=MIDNIGHT - timedelta(days=1))
    monkeypatch.setattr(propr_v12.time, "sleep", lambda _seconds: None)
    client = FakeClient(read_only=False)

    result = propr_v12.manage(now=NOW, client_factory=_factory(client))

    assert result["mode"] == "locked"
    assert result["production_ready"] is False
    assert result["reason"] == "missed_00utc_snapshot"
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["risk_memory"]["state"] == "LOCKED_TODAY"
    assert client.created == []


def test_live_gross_cap_breach_writes_lock_then_flattens(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path, manage=True, guard=True)
    _write_state(tmp_path)
    monkeypatch.setattr(propr_v12.time, "sleep", lambda _seconds: None)
    client = FakeClient(
        read_only=False,
        positions=[_position(notional="1800")],
    )

    result = propr_v12.manage(now=NOW, client_factory=_factory(client))

    assert result["mode"] == "locked"
    assert result["production_ready"] is False
    assert result["reason"] == "live_gross_cap_exceeded"
    assert result["actions"] == {"cancelled": 0, "flatten_orders": 1}
    assert client.created[0]["close_position"] is True
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["risk_memory"]["state"] == "LOCKED_TODAY"


def test_invalid_risk_input_is_latched_before_flat_recovery(tmp_path, monkeypatch):
    _set_env(monkeypatch, tmp_path, manage=True, guard=True)
    path = tmp_path / "state.json"
    propr_v12._write_state(
        path,
        DailySnapshot(
            account_id=ACCOUNT_ID,
            as_of_utc=MIDNIGHT,
            day_start_realized_balance=Decimal("0"),
            day_start_equity=Decimal("10000"),
        ),
        RiskMemory(account_id=ACCOUNT_ID),
    )
    monkeypatch.setattr(propr_v12.time, "sleep", lambda _seconds: None)
    client = FakeClient(read_only=False)

    result = propr_v12.manage(now=NOW, client_factory=_factory(client))

    assert result["mode"] == "flat_guarded"
    assert result["production_ready"] is False
    assert result["reason"].startswith("invalid_input:")
    state = json.loads(path.read_text())
    assert state["risk_memory"]["state"] == "LOCKED_TODAY"


def test_flatten_preserves_position_side_for_reduce_only_close(monkeypatch):
    monkeypatch.setattr(propr_v12.time, "sleep", lambda _seconds: None)
    client = FakeClient(
        read_only=False,
        positions=[_position(side="short")],
    )

    actions = propr_v12._recover_flat(client)

    assert actions == {"cancelled": 0, "flatten_orders": 1}
    assert client.created[0] == {
        "side": "buy",
        "position_side": "short",
        "order_type": "market",
        "asset": "BTC",
        "quantity": "0.01",
        "reduce_only": True,
        "close_position": True,
    }


def test_cli_error_explicitly_reports_not_production_ready(monkeypatch, capsys):
    def fail() -> dict:
        raise ProprError("test error")

    monkeypatch.setattr(sys, "argv", ["propr_v12.py", "--check"])
    monkeypatch.setattr(propr_v12, "check", fail)

    with pytest.raises(SystemExit) as exc:
        propr_v12.main()

    assert exc.value.code == 2
    assert json.loads(capsys.readouterr().out) == {
        "error": "test error",
        "mode": "error",
        "production_ready": False,
    }
