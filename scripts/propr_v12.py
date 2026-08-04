"""Fail-closed Propr Turbo 10k guard for the V12 one-third-risk candidate.

This is the bounded account/risk seam, not an always-on execution daemon.
``--check`` is read-only. ``--manage`` is disabled unless both V12 switches are
true; it may initialise pristine state or cancel and flatten exposure after a
no-new-orders risk decision. It never creates alpha exposure: a separate,
checker-approved target planner and a real-time WebSocket watchdog remain
required before production activation.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Context, Decimal, DecimalException, InvalidOperation, localcontext
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.propr_v12_signal import (  # noqa: E402
    CORE_SYMBOLS,
    LIVE_GROSS_MAX,
    MONDAY_UTC_MS,
    WEEK_MS,
)
from pipeline.live import atomic_write_text  # noqa: E402
from scripts.propr_client import ProprClient, ProprError  # noqa: E402
from scripts.propr_turbo_risk import (  # noqa: E402
    DailySnapshot,
    EquityObservation,
    OrderGate,
    RiskDecision,
    RiskMemory,
    RiskState,
    TURBO_10K_PROFILE,
    evaluate_risk,
)


STRATEGY_ID = "v12-turbo-third-risk-20260723-v2"
STATE_VERSION = "propr-v12-turbo-state-v1"
TARGET_SCHEMA_VERSION = 1
STATE_PATH = ROOT / "paper/propr_v12_turbo_state.json"
MAX_POSITIONS = len(CORE_SYMBOLS)
MAX_ACTIVE_ORDERS = 24
RECOVERY_ATTEMPTS = 3
FLAT_CONFIRMATIONS = 2
READBACK_DELAY_SECONDS = 0.25
EXIT_COST_RATE = Decimal("0.00325")  # 25 bps slippage + 7.5 bps fee
EXIT_RESERVE = Decimal("100")
TARGET_MAX_AGE = timedelta(minutes=15)
MAX_LIVE_GROSS_DOLLAR_TOLERANCE = Decimal("1")
LIVE_ASSET_CAP = Decimal("0.03333333333333333333333333333333333")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL_CONTEXT = Context(prec=34, Emin=-18, Emax=18)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ProprError(f"{name} obbligatoria")
    return value


def _state_path() -> Path:
    raw = os.environ.get("PROPR_V12_STATE_PATH", "").strip()
    return Path(raw).expanduser() if raw else STATE_PATH


def _challenge_slug() -> str:
    return _required_env("PROPR_V12_CHALLENGE_SLUG")


def _state_hmac_key() -> bytes:
    value = _required_env("PROPR_V12_STATE_HMAC_KEY")
    if len(value) < 32:
        raise ProprError("PROPR_V12_STATE_HMAC_KEY deve avere almeno 32 caratteri")
    return value.encode("utf-8")


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ProprError(f"{field} deve essere una stringa Decimal esatta")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
        with localcontext(_DECIMAL_CONTEXT) as context:
            checked = context.create_decimal(result)
    except (DecimalException, InvalidOperation, TypeError, ValueError) as exc:
        raise ProprError(f"{field} non valido") from exc
    if not checked.is_finite() or checked != result:
        raise ProprError(f"{field} non finito o fuori dominio")
    return checked


def _utc(value: object, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProprError(f"{field} non valido") from exc
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ProprError(f"{field} deve essere UTC")
    return value.astimezone(timezone.utc)


def _challenge_phase(challenge: dict) -> dict:
    phases = challenge.get("phases")
    if not isinstance(phases, list) or len(phases) != 1 or not isinstance(phases[0], dict):
        raise ProprError("challenge Turbo deve avere una sola fase")
    return phases[0]


def _validate_attempt(
    attempt: object,
    expected_account_id: str,
    expected_challenge_slug: str,
) -> None:
    if not isinstance(attempt, dict):
        raise ProprError("attempt Turbo assente")
    if attempt.get("accountId") != expected_account_id:
        raise ProprError("account Turbo diverso dal pin")
    if attempt.get("status") != "active":
        raise ProprError(f"attempt Turbo non attivo: {attempt.get('status')}")
    challenge = attempt.get("challenge")
    if not isinstance(challenge, dict):
        raise ProprError("metadati challenge Turbo assenti")
    slug = str(challenge.get("slug", "")).lower()
    name = str(challenge.get("name", "")).lower()
    if slug != expected_challenge_slug.lower():
        raise ProprError("challenge Turbo diversa dal pin esatto")
    if "free-trial" in slug or "turbo" not in f"{slug} {name}":
        raise ProprError("challenge non identificata come Turbo")
    if _decimal(challenge.get("initialBalance"), "initialBalance") != Decimal("10000"):
        raise ProprError("balance iniziale Turbo diverso da 10000")
    phase = _challenge_phase(challenge)
    expected = {
        "profitTargetPercent": Decimal("9"),
        "maxDailyLossPercent": Decimal("3"),
        "maxDrawdownPercent": Decimal("3"),
    }
    for field, wanted in expected.items():
        if _decimal(phase.get(field), field) != wanted:
            raise ProprError(f"regola Turbo inattesa: {field}")
    drawdown_type = phase.get("drawdownType", challenge.get("drawdownType"))
    if drawdown_type is not None and str(drawdown_type).lower() != "static":
        raise ProprError("drawdown Turbo non statico")


def _validate_positions(positions: object) -> list[dict]:
    if not isinstance(positions, list) or len(positions) > MAX_POSITIONS:
        raise ProprError("lista posizioni V12 non valida")
    seen: set[str] = set()
    checked: list[dict] = []
    for position in positions:
        if not isinstance(position, dict):
            raise ProprError("posizione V12 non strutturata")
        asset = str(position.get("base", "")).upper()
        if asset not in CORE_SYMBOLS or asset in seen:
            raise ProprError(f"asset V12 inatteso o duplicato: {asset}")
        seen.add(asset)
        side = str(position.get("positionSide", "")).lower()
        if side not in ("long", "short"):
            raise ProprError(f"positionSide V12 non valido: {asset}")
        if str(position.get("marginMode", "")).lower() != "cross":
            raise ProprError(f"margine non cross: {asset}")
        quantity = abs(_decimal(position.get("quantity"), f"quantity {asset}"))
        notional = abs(_decimal(position.get("notionalValue"), f"notionalValue {asset}"))
        mark = _decimal(position.get("markPrice"), f"markPrice {asset}")
        if quantity <= 0 or notional <= 0 or mark <= 0 or not position.get("positionId"):
            raise ProprError(f"schema posizione V12 non valido: {asset}")
        checked.append(position)
    return checked


def _validate_orders(orders: object) -> list[dict]:
    if not isinstance(orders, list) or len(orders) > MAX_ACTIVE_ORDERS:
        raise ProprError("lista ordini V12 non valida")
    ids: set[str] = set()
    for order in orders:
        order_id = order.get("orderId") if isinstance(order, dict) else None
        if not isinstance(order_id, str) or not order_id or order_id in ids:
            raise ProprError("ordine V12 attivo senza id univoco")
        ids.add(order_id)
    return orders


def _account_values(account: object) -> tuple[Decimal, Decimal]:
    if not isinstance(account, dict):
        raise ProprError("account Turbo non strutturato")
    balance = _decimal(account.get("balance"), "account.balance")
    unrealized = _decimal(
        account.get("totalUnrealizedPnl", "0"),
        "account.totalUnrealizedPnl",
    )
    isolated = _decimal(
        account.get("isolatedPositionMargin", "0"),
        "account.isolatedPositionMargin",
    )
    if balance <= 0 or isolated != 0:
        raise ProprError("account non positivo o con margine isolato")
    try:
        with localcontext(_DECIMAL_CONTEXT):
            equity = balance + unrealized + isolated
    except DecimalException as exc:
        raise ProprError("equity account fuori dominio") from exc
    if not equity.is_finite() or equity <= 0:
        raise ProprError("equity account non valida")
    for field in ("equity", "marginBalance"):
        if field in account and _decimal(account[field], f"account.{field}") != equity:
            raise ProprError(f"account.{field} non coincide con l'equity calcolata")
    return balance, equity


def _stressed_flatten_cost(positions: list[dict]) -> Decimal:
    try:
        with localcontext(_DECIMAL_CONTEXT):
            gross = sum(
                (abs(_decimal(item["notionalValue"], "notionalValue")) for item in positions),
                Decimal("0"),
            )
            cost = gross * EXIT_COST_RATE
    except DecimalException as exc:
        raise ProprError("stima flatten fuori dominio") from exc
    if not cost.is_finite() or cost < 0:
        raise ProprError("stima flatten non valida")
    return cost


def _gross_notional(positions: list[dict]) -> Decimal:
    try:
        with localcontext(_DECIMAL_CONTEXT):
            gross = sum(
                (abs(_decimal(item["notionalValue"], "notionalValue")) for item in positions),
                Decimal("0"),
            )
    except DecimalException as exc:
        raise ProprError("gross live fuori dominio") from exc
    if not gross.is_finite() or gross < 0:
        raise ProprError("gross live non valido")
    return gross


def _gross_limit(equity: Decimal) -> Decimal:
    try:
        with localcontext(_DECIMAL_CONTEXT):
            limit = equity * Decimal(LIVE_GROSS_MAX.numerator) / Decimal(
                LIVE_GROSS_MAX.denominator
            )
    except DecimalException as exc:
        raise ProprError("cap gross live fuori dominio") from exc
    if not limit.is_finite() or limit <= 0:
        raise ProprError("cap gross live non valido")
    return limit


def _snapshot_payload(snapshot: DailySnapshot) -> dict:
    return {
        "account_id": snapshot.account_id,
        "as_of_utc": snapshot.as_of_utc.isoformat().replace("+00:00", "Z"),
        "day_start_realized_balance": str(snapshot.day_start_realized_balance),
        "day_start_equity": str(snapshot.day_start_equity),
    }


def _memory_payload(memory: RiskMemory) -> dict:
    return {
        "account_id": memory.account_id,
        "state": memory.state.value,
        "locked_utc_date": (
            memory.locked_utc_date.isoformat()
            if memory.locked_utc_date is not None
            else None
        ),
    }


def _state_payload(snapshot: DailySnapshot, memory: RiskMemory) -> dict:
    return {
        "version": STATE_VERSION,
        "strategy_id": STRATEGY_ID,
        "account_id": snapshot.account_id,
        "snapshot": _snapshot_payload(snapshot),
        "risk_memory": _memory_payload(memory),
    }


def _canonical(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _signed_state_payload(snapshot: DailySnapshot, memory: RiskMemory) -> dict:
    payload = _state_payload(snapshot, memory)
    signature = hmac.new(
        _state_hmac_key(),
        _canonical(payload),
        hashlib.sha256,
    ).hexdigest()
    return {**payload, "hmac_sha256": signature}


def _write_state(path: Path, snapshot: DailySnapshot, memory: RiskMemory) -> None:
    atomic_write_text(
        path,
        json.dumps(
            _signed_state_payload(snapshot, memory),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def _read_state(path: Path, expected_account_id: str) -> tuple[DailySnapshot, RiskMemory]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProprError("stato V12 illeggibile") from exc
    if not isinstance(payload, dict):
        raise ProprError("stato V12 non strutturato")
    signature = payload.get("hmac_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "hmac_sha256"}
    expected_signature = hmac.new(
        _state_hmac_key(),
        _canonical(unsigned),
        hashlib.sha256,
    ).hexdigest()
    if (
        not isinstance(signature, str)
        or not _HASH.fullmatch(signature)
        or not hmac.compare_digest(signature, expected_signature)
    ):
        raise ProprError("integrita HMAC stato V12 non valida")
    required = {
        "version": STATE_VERSION,
        "strategy_id": STRATEGY_ID,
        "account_id": expected_account_id,
    }
    if any(payload.get(key) != value for key, value in required.items()):
        raise ProprError("stato V12 incompatibile")
    raw_snapshot = payload.get("snapshot")
    raw_memory = payload.get("risk_memory")
    if not isinstance(raw_snapshot, dict) or not isinstance(raw_memory, dict):
        raise ProprError("stato V12 incompleto")
    try:
        snapshot = DailySnapshot(
            account_id=str(raw_snapshot["account_id"]),
            as_of_utc=_utc(raw_snapshot["as_of_utc"], "snapshot.as_of_utc"),
            day_start_realized_balance=_decimal(
                raw_snapshot["day_start_realized_balance"],
                "snapshot.day_start_realized_balance",
            ),
            day_start_equity=_decimal(
                raw_snapshot["day_start_equity"],
                "snapshot.day_start_equity",
            ),
        )
        locked = raw_memory.get("locked_utc_date")
        memory = RiskMemory(
            account_id=raw_memory.get("account_id"),
            state=RiskState(raw_memory["state"]),
            locked_utc_date=date.fromisoformat(locked) if locked else None,
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise ProprError("stato V12 malformato") from exc
    if snapshot.account_id != expected_account_id or memory.account_id not in (
        None,
        expected_account_id,
    ):
        raise ProprError("account nello stato V12 non coincide col pin")
    return snapshot, memory


def _midnight(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _new_snapshot(
    *,
    account_id: str,
    now: datetime,
    balance: Decimal,
    equity: Decimal,
) -> DailySnapshot:
    return DailySnapshot(account_id, _midnight(now), balance, equity)


def _pristine(
    balance: Decimal,
    equity: Decimal,
    positions: list[dict],
    orders: list[dict],
) -> bool:
    return (
        balance == TURBO_10K_PROFILE.starting_balance
        and equity == TURBO_10K_PROFILE.starting_balance
        and not positions
        and not orders
    )


def _current_snapshot(
    *,
    prior: DailySnapshot,
    memory: RiskMemory,
    account_id: str,
    now: datetime,
    balance: Decimal,
    equity: Decimal,
) -> DailySnapshot:
    if prior.as_of_utc.date() == now.date():
        return prior
    if memory.state is RiskState.HALT_ACCOUNT:
        return _new_snapshot(
            account_id=account_id,
            now=now,
            balance=balance,
            equity=equity,
        )
    within_midnight_tick = now - _midnight(now) <= timedelta(seconds=2)
    if within_midnight_tick:
        return _new_snapshot(
            account_id=account_id,
            now=now,
            balance=balance,
            equity=equity,
        )
    raise ProprError("snapshot 00UTC perso: baseline giornaliera non ricostruibile")


def _decision_payload(decision: RiskDecision) -> dict:
    return {
        "state": decision.state.value,
        "order_gate": decision.order_gate.value,
        "reason": decision.reason,
        "target_reached": decision.target_reached,
        "realized_balance": (
            str(decision.realized_balance)
            if decision.realized_balance is not None
            else None
        ),
        "liquidation_adjusted_equity": (
            str(decision.liquidation_adjusted_equity)
            if decision.liquidation_adjusted_equity is not None
            else None
        ),
        "hard_floor": str(decision.hard_floor) if decision.hard_floor is not None else None,
        "soft_floor": str(decision.soft_floor) if decision.soft_floor is not None else None,
    }


def _flatten_position(client: ProprClient, position: dict) -> None:
    is_short = str(position["positionSide"]).lower() == "short"
    side = "buy" if is_short else "sell"
    position_side = "short" if is_short else "long"
    quantity = format(abs(_decimal(position["quantity"], "flatten.quantity")), "f")
    response = client.create_order(
        side=side,
        position_side=position_side,
        order_type="market",
        asset=str(position["base"]).upper(),
        quantity=quantity,
        reduce_only=True,
        close_position=True,
    )
    if not isinstance(response, list) or len(response) != 1:
        raise ProprError(f"flatten non verificabile: {position['base']}")
    status = response[0].get("status") if isinstance(response[0], dict) else None
    if status not in ("pending", "open", "partially_filled", "filled"):
        raise ProprError(f"flatten rifiutato: {position['base']} status={status}")


def _recover_flat(client: ProprClient) -> dict:
    actions = {"cancelled": 0, "flatten_orders": 0}
    confirmations = 0
    last_error: Exception | None = None
    for attempt in range(RECOVERY_ATTEMPTS):
        try:
            orders = _validate_orders(client.get_active_orders())
            for order in orders:
                client.cancel_order(str(order["orderId"]))
                actions["cancelled"] += 1
            positions = _validate_positions(client.get_positions())
            for position in positions:
                _flatten_position(client, position)
                actions["flatten_orders"] += 1
            time.sleep(READBACK_DELAY_SECONDS)
            remaining_orders = _validate_orders(client.get_active_orders())
            remaining_positions = _validate_positions(client.get_positions())
            if not remaining_orders and not remaining_positions:
                confirmations += 1
                if confirmations >= FLAT_CONFIRMATIONS:
                    return actions
            else:
                confirmations = 0
        except Exception as exc:  # recovery must continue through transient API errors
            last_error = exc
            confirmations = 0
        if attempt + 1 < RECOVERY_ATTEMPTS:
            time.sleep(READBACK_DELAY_SECONDS)
    suffix = f": {last_error}" if last_error is not None else ""
    raise ProprError(f"flat V12 non confermato dopo recovery{suffix}")


def _target_contract(path: Path, *, account_id: str, now: datetime) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProprError("target V12 illeggibile") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != TARGET_SCHEMA_VERSION:
        raise ProprError("target V12 con schema inatteso")
    if payload.get("strategy_id") != STRATEGY_ID or payload.get("account_id") != account_id:
        raise ProprError("target V12 non legato a strategia/account")
    created = _utc(payload.get("created_at_utc"), "target.created_at_utc")
    if now < created or now - created > TARGET_MAX_AGE:
        raise ProprError("target V12 futuro o stale")
    anchor = payload.get("weekly_anchor_ms")
    if type(anchor) is not int or (anchor - MONDAY_UTC_MS) % WEEK_MS:
        raise ProprError("anchor settimanale V12 non valido")
    current_monday = _midnight(now) - timedelta(days=now.weekday())
    if anchor != int(current_monday.timestamp() * 1000):
        raise ProprError("target V12 non appartiene alla settimana UTC corrente")
    expected_hashes = {
        "source_freeze_sha256": _required_env("PROPR_V12_SOURCE_FREEZE_SHA256"),
        "checker_receipt_sha256": _required_env("PROPR_V12_CHECKER_RECEIPT_SHA256"),
    }
    for field, expected_hash in expected_hashes.items():
        if not _HASH.fullmatch(expected_hash):
            raise ProprError(f"pin env {field} non valido")
        if payload.get(field) != expected_hash:
            raise ProprError(f"{field} target V12 non valido")
    raw_weights = payload.get("weights")
    if not isinstance(raw_weights, dict) or set(raw_weights) != set(CORE_SYMBOLS):
        raise ProprError("weights target V12 incompleti")
    weights = {symbol: _decimal(raw_weights[symbol], f"weight {symbol}") for symbol in CORE_SYMBOLS}
    if any(abs(value) > LIVE_ASSET_CAP for value in weights.values()):
        raise ProprError("cap per-asset target V12 superato")
    try:
        with localcontext(_DECIMAL_CONTEXT):
            gross = sum((abs(value) for value in weights.values()), Decimal("0"))
            gross_cap = Decimal(LIVE_GROSS_MAX.numerator) / Decimal(
                LIVE_GROSS_MAX.denominator
            )
    except DecimalException as exc:
        raise ProprError("gross target V12 fuori dominio") from exc
    if gross > gross_cap:
        raise ProprError("gross target V12 superato")
    return {**payload, "weights": {key: str(value) for key, value in weights.items()}}


def _client(*, read_only: bool) -> ProprClient:
    return ProprClient(
        api_key=_required_env("PROPR_V12_API_KEY"),
        read_only=read_only,
    )


def _account_id() -> str:
    return _required_env("PROPR_V12_ACCOUNT_ID")


def _observe(
    client: ProprClient,
    *,
    account_id: str,
    clock: Callable[[], datetime],
) -> tuple[
    dict,
    list[dict],
    list[dict],
    Decimal,
    Decimal,
    Decimal,
    EquityObservation,
]:
    account = client.get_account()
    positions = _validate_positions(client.get_positions())
    orders = _validate_orders(client.get_active_orders())
    balance, equity = _account_values(account)
    gross = _gross_notional(positions)
    observed_at = _utc(clock(), "rest_snapshot_received_at")
    observation = EquityObservation(
        account_id=account_id,
        observed_at_utc=observed_at,
        realized_balance=balance,
        equity=equity,
        stressed_flatten_cost=_stressed_flatten_cost(positions),
    )
    return account, positions, orders, balance, equity, gross, observation


def _setup(client: ProprClient, account_id: str, challenge_slug: str) -> None:
    client.setup(
        expected_account_id=account_id,
        expected_challenge_slug=challenge_slug,
    )
    _validate_attempt(client.active_attempt, account_id, challenge_slug)


def check(
    *,
    now: datetime | None = None,
    client_factory: Callable[..., ProprClient] = _client,
) -> dict:
    """Read-only preflight; it never creates state or sends an order."""

    fixed_now = _utc(now, "now") if now is not None else None
    clock = (lambda: fixed_now) if fixed_now is not None else _now
    account_id = _account_id()
    challenge_slug = _challenge_slug()
    client = client_factory(read_only=True)
    _setup(client, account_id, challenge_slug)
    _, positions, orders, balance, equity, gross, observation = _observe(
        client,
        account_id=account_id,
        clock=clock,
    )
    observed_at = observation.observed_at_utc
    gross_limit = _gross_limit(equity)
    if gross > gross_limit + MAX_LIVE_GROSS_DOLLAR_TOLERANCE:
        return {
            "mode": "check",
            "ready": False,
            "production_ready": False,
            "reason": "live_gross_cap_exceeded",
            "writes": 0,
            "account_id": account_id,
            "positions": len(positions),
            "active_orders": len(orders),
            "gross": str(gross),
            "gross_limit": str(gross_limit),
        }
    path = _state_path()
    if not path.exists():
        return {
            "mode": "check",
            "ready": False,
            "production_ready": False,
            "reason": (
                "pristine_state_initialization_required"
                if _pristine(balance, equity, positions, orders)
                else "state_missing_non_pristine"
            ),
            "writes": 0,
            "account_id": account_id,
            "positions": len(positions),
            "active_orders": len(orders),
        }
    snapshot, memory = _read_state(path, account_id)
    try:
        snapshot = _current_snapshot(
            prior=snapshot,
            memory=memory,
            account_id=account_id,
            now=observed_at,
            balance=balance,
            equity=equity,
        )
        decision = evaluate_risk(
            expected_account_id=account_id,
            now_utc=observed_at,
            snapshot=snapshot,
            observation=observation,
            memory=memory,
            exit_reserve=EXIT_RESERVE,
        )
    except ProprError as exc:
        return {
            "mode": "check",
            "ready": False,
            "production_ready": False,
            "reason": str(exc),
            "writes": 0,
            "account_id": account_id,
            "positions": len(positions),
            "active_orders": len(orders),
        }
    return {
        "mode": "check",
        "ready": False,
        "risk_gate_ready": decision.order_gate is OrderGate.ALLOW_NEW_ORDERS,
        "production_ready": False,
        "production_blocker": "realtime_websocket_watchdog_and_entry_executor_missing",
        "writes": 0,
        "account_id": account_id,
        "positions": len(positions),
        "active_orders": len(orders),
        "decision": _decision_payload(decision),
    }


def manage(
    *,
    now: datetime | None = None,
    client_factory: Callable[..., ProprClient] = _client,
) -> dict:
    """One guarded REST tick. No alpha-entry path exists in this bounded seam."""

    if not _enabled("PROPR_V12_AUTOMANAGE_ENABLED"):
        return {"mode": "disabled", "production_ready": False, "writes": 0}
    if not _enabled("PROPR_V12_GUARD_ENABLED"):
        raise ProprError("PROPR_V12_GUARD_ENABLED non attivo")

    fixed_now = _utc(now, "now") if now is not None else None
    clock = (lambda: fixed_now) if fixed_now is not None else _now
    account_id = _account_id()
    challenge_slug = _challenge_slug()
    client = client_factory(read_only=False)
    _setup(client, account_id, challenge_slug)
    _, positions, orders, balance, equity, gross, observation = _observe(
        client,
        account_id=account_id,
        clock=clock,
    )
    observed_at = observation.observed_at_utc
    gross_limit = _gross_limit(equity)
    path = _state_path()
    if path.exists():
        snapshot, memory = _read_state(path, account_id)
    else:
        if not _pristine(balance, equity, positions, orders):
            raise ProprError("prima attivazione V12 non pristine")
        snapshot = _new_snapshot(
            account_id=account_id,
            now=observed_at,
            balance=balance,
            equity=equity,
        )
        memory = RiskMemory(account_id=account_id)

    if gross > gross_limit + MAX_LIVE_GROSS_DOLLAR_TOLERANCE:
        emergency_memory = RiskMemory(
            account_id=account_id,
            state=RiskState.LOCKED_TODAY,
            locked_utc_date=observed_at.date(),
        )
        emergency_snapshot = (
            snapshot
            if snapshot.as_of_utc.date() == observed_at.date()
            else _new_snapshot(
                account_id=account_id,
                now=observed_at,
                balance=balance,
                equity=equity,
            )
        )
        _write_state(path, emergency_snapshot, emergency_memory)
        actions = _recover_flat(client)
        return {
            "mode": "locked",
            "production_ready": False,
            "reason": "live_gross_cap_exceeded",
            "writes": 1 + actions["cancelled"] + actions["flatten_orders"],
            "gross": str(gross),
            "gross_limit": str(gross_limit),
            "actions": actions,
        }

    try:
        snapshot = _current_snapshot(
            prior=snapshot,
            memory=memory,
            account_id=account_id,
            now=observed_at,
            balance=balance,
            equity=equity,
        )
    except ProprError:
        emergency_memory = RiskMemory(
            account_id=account_id,
            state=RiskState.LOCKED_TODAY,
            locked_utc_date=observed_at.date(),
        )
        emergency_snapshot = _new_snapshot(
            account_id=account_id,
            now=observed_at,
            balance=balance,
            equity=equity,
        )
        _write_state(path, emergency_snapshot, emergency_memory)
        actions = _recover_flat(client)
        return {
            "mode": "locked",
            "production_ready": False,
            "reason": "missed_00utc_snapshot",
            "writes": 1 + actions["cancelled"] + actions["flatten_orders"],
            "actions": actions,
        }

    decision = evaluate_risk(
        expected_account_id=account_id,
        now_utc=observed_at,
        snapshot=snapshot,
        observation=observation,
        memory=memory,
        exit_reserve=EXIT_RESERVE,
    )
    persisted_memory = decision.next_memory
    if (
        decision.order_gate is OrderGate.NO_NEW_ORDERS
        and decision.reason.startswith("invalid_input:")
        and persisted_memory.state is RiskState.ACTIVE
    ):
        persisted_memory = RiskMemory(
            account_id=account_id,
            state=RiskState.LOCKED_TODAY,
            locked_utc_date=observed_at.date(),
        )
    _write_state(path, snapshot, persisted_memory)
    if decision.order_gate is OrderGate.NO_NEW_ORDERS:
        actions = _recover_flat(client)
        return {
            "mode": "flat_guarded",
            "production_ready": False,
            "reason": decision.reason,
            "writes": 1 + actions["cancelled"] + actions["flatten_orders"],
            "decision": _decision_payload(decision),
            "actions": actions,
        }

    target_path = os.environ.get("PROPR_V12_TARGET_PATH", "").strip()
    if not target_path:
        return {
            "mode": "armed_no_target",
            "production_ready": False,
            "reason": "target_contract_required",
            "writes": 1,
            "decision": _decision_payload(decision),
            "orders_created": 0,
        }
    target = _target_contract(Path(target_path), account_id=account_id, now=observed_at)
    nonzero = sum(1 for value in target["weights"].values() if Decimal(value) != 0)
    return {
        "mode": "target_validated_execution_disabled",
        "production_ready": False,
        "reason": "entry_executor_and_realtime_watchdog_not_implemented",
        "writes": 1,
        "decision": _decision_payload(decision),
        "target_nonzero_weights": nonzero,
        "orders_created": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--manage", action="store_true")
    args = parser.parse_args()
    try:
        result = check() if args.check else manage()
    except ProprError as exc:
        print(
            json.dumps(
                {"mode": "error", "production_ready": False, "error": str(exc)},
                sort_keys=True,
            )
        )
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
