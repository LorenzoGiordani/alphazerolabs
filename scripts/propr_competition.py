"""Runner cloud fail-closed per il Lighter x Propr Trading Tournament.

La corsia e' separata dal Free Trial: usa un account pin dedicato, stato e
journal dedicati e una strategia TSMOM deterministica. ``--check`` e' sempre
read-only; ``--manage`` puo' scrivere solo quando il kill switch competition e'
esplicitamente attivo e la finestra UTC del torneo e' aperta.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.portfolio import sign_weights  # noqa: E402
from pipeline.live import atomic_write_text  # noqa: E402
from scripts.portfolio_paper import trailing_returns  # noqa: E402
from scripts.propr_client import ProprClient, ProprError  # noqa: E402
from scripts.propr_paper import flatten, rebalance  # noqa: E402


COMPETITION_ID = "urn:prp-competition:XSLPfvuHDUtT"
COMPETITION_SLUG = "lighter-propr-trading-tournament"
STRATEGY_ID = "tsmom-neutral-tournament-20260723-v1"
START_AT = datetime(2026, 7, 23, 13, 0, tzinfo=timezone.utc)
# Due run utili prima dello stop: il clock cloud gira ogni ora al minuto :10.
FLATTEN_AT = datetime(2026, 7, 30, 11, 0, tzinfo=timezone.utc)
END_AT = datetime(2026, 7, 30, 13, 0, tzinfo=timezone.utc)
EXPECTED_INITIAL_BALANCE = Decimal("50000")
SYMBOLS = ("BTC", "ETH", "SOL", "XRP", "SUI", "NEAR")
LOOKBACK_H = 168
REBALANCE_H = 24
GROSS = 0.30
DAILY_STOP_PCT = 0.015
TOTAL_STOP_PCT = 0.04
STOP_DISTANCE = Decimal("0.04")
RECONCILE_REL_TOL = 0.05
RECONCILE_ABS_TOL = 25.0
RUNTIME_RECONCILE_REL_TOL = 0.35
RUNTIME_RECONCILE_ABS_TOL = 100.0
QUANTITY_REL_TOL = Decimal("0.01")
MAX_POSITIONS = len(SYMBOLS)
MAX_GUARD_CREATES = 8
MAX_CANCELS = 12
FLAT_READBACKS = 3
FLAT_CONFIRMATIONS = 2
RECOVERY_ATTEMPTS = 3
STATE_VERSION = "propr-competition-state-v2"
STOP_VERSION = "propr-competition-stop-v1"
_FALLBACK_ULID_MS = 1_577_836_800_000
_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

STATE_PATH = ROOT / "paper/propr_competition_state.json"
STATUS_PATH = ROOT / "paper/propr_competition_status.json"
JOURNAL_PATH = ROOT / "paper/propr_competition_journal.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


def _guard_enabled() -> bool:
    return _enabled("PROPR_COMPETITION_GUARD_ENABLED")


def _automanage_enabled() -> bool:
    return _enabled("PROPR_COMPETITION_AUTOMANAGE_ENABLED")


def _account_id() -> str:
    value = os.environ.get("PROPR_COMPETITION_ACCOUNT_ID", "").strip()
    if not value:
        raise ProprError("PROPR_COMPETITION_ACCOUNT_ID obbligatorio")
    return value


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProprError(f"{field} non valido: {value}") from exc
    if not result.is_finite():
        raise ProprError(f"{field} non finito: {value}")
    return result


def _timestamp(value: object, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ProprError(f"{field} non valido: {value}") from exc
    if result.tzinfo is None:
        raise ProprError(f"{field} senza timezone: {value}")
    return result.astimezone(timezone.utc)


def _five_significant(value: Decimal) -> str:
    if value <= 0:
        raise ProprError(f"trigger price non valido: {value}")
    quantum = Decimal(1).scaleb(value.adjusted() - 4)
    rounded = value.quantize(quantum)
    rendered = format(rounded, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _ulid_from_bytes(value: bytes) -> str:
    number = int.from_bytes(value, "big")
    encoded = ["0"] * 26
    for index in range(25, -1, -1):
        encoded[index] = _CROCKFORD32[number & 31]
        number >>= 5
    return "".join(encoded)


def _created_at_ms(position: dict) -> int:
    raw = position.get("createdAt") or position.get("openedAt")
    if not raw:
        return _FALLBACK_ULID_MS
    try:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        milliseconds = int(stamp.timestamp() * 1000)
    except (TypeError, ValueError, OverflowError):
        return _FALLBACK_ULID_MS
    return min(max(milliseconds, 0), (1 << 48) - 1)


def _stop_intent_id(position: dict) -> str:
    quantity = format(abs(_decimal(position.get("quantity"), "quantity stop")), "f")
    seed = "|".join((
        STOP_VERSION,
        str(position["positionId"]),
        str(position["positionSide"]).lower(),
        quantity,
    )).encode()
    randomness = hashlib.sha256(seed).digest()[:10]
    value = _created_at_ms(position).to_bytes(6, "big") + randomness
    return _ulid_from_bytes(value)


def _stop_plan(position: dict) -> dict:
    asset = str(position.get("base", "")).upper()
    position_id = str(position.get("positionId", ""))
    side = str(position.get("positionSide", "")).lower()
    if not asset or not position_id or side not in ("long", "short"):
        raise ProprError("posizione competition non proteggibile")
    quantity_value = abs(_decimal(position.get("quantity"), f"quantity {asset}"))
    if quantity_value == 0:
        raise ProprError(f"quantity nulla per {asset}")
    reference = _decimal(position.get("entryPrice"), f"entryPrice {asset}")
    closing_side = "sell" if side == "long" else "buy"
    multiplier = Decimal("1") - STOP_DISTANCE if side == "long" else Decimal("1") + STOP_DISTANCE
    return {
        "asset": asset,
        "position_id": position_id,
        "side": closing_side,
        "position_side": "short" if closing_side == "sell" else "long",
        "quantity": format(quantity_value, "f"),
        "trigger_price": _five_significant(reference * multiplier),
        "intent_id": _stop_intent_id(position),
    }


def _is_exact_protection(position: dict, order: dict) -> bool:
    try:
        plan = _stop_plan(position)
        order_quantity = abs(_decimal(order.get("quantity"), "quantity stop attivo"))
        trigger = _decimal(order.get("triggerPrice"), "triggerPrice stop attivo")
        planned_trigger = _decimal(plan["trigger_price"], "triggerPrice stop pianificato")
    except ProprError:
        return False
    return bool(
        order.get("type") == "stop_market"
        and str(order.get("positionId", "")) == plan["position_id"]
        and str(order.get("intentId", "")) == plan["intent_id"]
        and str(order.get("side", "")).lower() == plan["side"]
        and str(order.get("positionSide", "")).lower() == plan["position_side"]
        and order.get("reduceOnly") is True
        and order.get("closePosition") is True
        and order_quantity == _decimal(plan["quantity"], "quantity stop pianificato")
        and trigger == planned_trigger
        and not _stop_is_crossed(position, trigger)
    )


def _stop_is_crossed(position: dict, trigger: Decimal) -> bool:
    mark = _decimal(position.get("markPrice"), "markPrice posizione")
    side = str(position.get("positionSide", "")).lower()
    return mark <= trigger if side == "long" else mark >= trigger


def _competition_ids(attempt: dict) -> set[str]:
    values = {attempt.get("competitionId")}
    competition = attempt.get("competition")
    if isinstance(competition, dict):
        values.update((competition.get("id"), competition.get("competitionId")))
    return {str(value) for value in values if value}


def _validate_attempt(attempt: dict | None, expected_account_id: str) -> None:
    if not attempt:
        raise ProprError("attempt competition attivo assente")
    if attempt.get("status") != "active":
        raise ProprError(f"attempt competition non attivo: {attempt.get('status')}")
    if attempt.get("accountId") != expected_account_id:
        raise ProprError(f"account competition inatteso: {attempt.get('accountId')}")
    challenge = attempt.get("challenge")
    if not isinstance(challenge, dict):
        raise ProprError("metadati challenge competition assenti")
    if challenge.get("slug") == "free-trial":
        raise ProprError("rifiutato account Free Trial nella corsia competition")
    balance = _decimal(challenge.get("initialBalance"), "initialBalance")
    if balance != EXPECTED_INITIAL_BALANCE:
        raise ProprError(f"balance iniziale competition inatteso: {balance}")
    competition = attempt.get("competition")
    if not isinstance(competition, dict):
        raise ProprError("metadati competition assenti")
    if competition.get("exchange") != "hyperliquid":
        raise ProprError(f"exchange competition inatteso: {competition.get('exchange')}")
    if competition.get("currency") != "USDC":
        raise ProprError(f"currency competition inattesa: {competition.get('currency')}")
    if competition.get("slug") != COMPETITION_SLUG:
        raise ProprError(f"slug competition inatteso: {competition.get('slug')}")
    if _timestamp(competition.get("startsAt"), "startsAt") != START_AT:
        raise ProprError(f"startsAt competition inatteso: {competition.get('startsAt')}")
    if _timestamp(competition.get("endsAt"), "endsAt") != END_AT:
        raise ProprError(f"endsAt competition inatteso: {competition.get('endsAt')}")
    observed_ids = _competition_ids(attempt)
    if observed_ids != {COMPETITION_ID}:
        raise ProprError(f"competition id inatteso: {sorted(observed_ids)}")


def _validate_positions(positions: list[dict]) -> None:
    if len(positions) > MAX_POSITIONS:
        raise ProprError(f"troppe posizioni competition: {len(positions)} > {MAX_POSITIONS}")
    unexpected = sorted({str(position.get("base", "")) for position in positions} - set(SYMBOLS))
    if unexpected:
        raise ProprError(f"posizioni estranee alla strategia competition: {','.join(unexpected)}")
    for position in positions:
        if str(position.get("positionSide", "")).lower() not in ("long", "short"):
            raise ProprError(f"positionSide inatteso per {position.get('base')}")
        asset = str(position.get("base", ""))
        if not position.get("positionId"):
            raise ProprError(f"positionId assente per {asset}")
        quantity = abs(_decimal(position.get("quantity"), f"quantity {asset}"))
        entry = _decimal(position.get("entryPrice"), f"entryPrice {asset}")
        mark = _decimal(position.get("markPrice"), f"markPrice {asset}")
        notional = _decimal(position.get("notionalValue"), f"notionalValue {asset}")
        _decimal(position.get("unrealizedPnl", 0), f"unrealizedPnl {asset}")
        if quantity == 0 or entry <= 0 or mark <= 0 or notional < 0:
            raise ProprError(f"schema posizione non valido per {asset}")


def _read_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(STATE_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ProprError("stato competition illeggibile") from exc
    if not isinstance(payload, dict):
        raise ProprError("stato competition non valido")
    return payload


def _fresh_state(account_id: str, equity: float, now: datetime) -> dict:
    return {
        "version": STATE_VERSION,
        "competition_id": COMPETITION_ID,
        "strategy": STRATEGY_ID,
        "account_id": account_id,
        "activated_at": now.isoformat(),
        "day_date": now.date().isoformat(),
        "day_start_equity": round(equity, 8),
        "last_equity": round(equity, 8),
        "high_water_mark": round(equity, 8),
        "halted_today": False,
        "halt_kind": "",
        "halt_reason": "",
        "permanently_halted": False,
        "last_rebalance_ts": "",
        "last_target": {},
        "expected_assets": [],
        "expected_sides": {},
        "expected_quantities": {},
    }


def _validate_state(state: dict, account_id: str) -> None:
    required = {
        "version": STATE_VERSION,
        "competition_id": COMPETITION_ID,
        "strategy": STRATEGY_ID,
        "account_id": account_id,
    }
    mismatches = [key for key, value in required.items() if state.get(key) != value]
    if mismatches:
        raise ProprError(f"stato competition incompatibile: {','.join(mismatches)}")

    for key in ("halted_today", "permanently_halted"):
        if type(state.get(key)) is not bool:
            raise ProprError(f"stato competition {key} non booleano")
    if state.get("halt_kind") not in ("", "daily", "operational"):
        raise ProprError("stato competition halt_kind non valido")
    if not isinstance(state.get("halt_reason"), str):
        raise ProprError("stato competition halt_reason non valido")
    halted = state["halted_today"]
    permanent = state["permanently_halted"]
    if permanent and (not halted or state["halt_kind"] != "operational"):
        raise ProprError("stato competition halt permanente incoerente")
    if state["halt_kind"] == "operational" and not permanent:
        raise ProprError("stato competition halt operativo non permanente")
    if (halted and (not state["halt_kind"] or not state["halt_reason"])) or (
        not halted and (state["halt_kind"] or state["halt_reason"])
    ):
        raise ProprError("stato competition halt incompleto")

    numeric_state = {}
    for key in ("day_start_equity", "last_equity", "high_water_mark"):
        numeric_state[key] = _decimal(state.get(key), f"state {key}")
        if numeric_state[key] <= 0:
            raise ProprError(f"stato competition {key} non positivo")
    if numeric_state["high_water_mark"] < EXPECTED_INITIAL_BALANCE:
        raise ProprError("stato competition high_water_mark sotto balance iniziale")
    static_floor = EXPECTED_INITIAL_BALANCE * Decimal(str(1.0 - TOTAL_STOP_PCT))
    if numeric_state["day_start_equity"] < static_floor:
        raise ProprError("stato competition day_start_equity sotto floor")
    if not permanent and numeric_state["last_equity"] <= static_floor:
        raise ProprError("stato competition equity sotto floor senza halt permanente")
    try:
        datetime.strptime(str(state.get("day_date")), "%Y-%m-%d")
    except ValueError as exc:
        raise ProprError("stato competition day_date non valido") from exc
    for key in ("activated_at", "last_rebalance_ts", "last_manage_ts"):
        raw = state.get(key, "")
        if key == "activated_at" and not raw:
            raise ProprError("stato competition activated_at assente")
        if not raw:
            continue
        try:
            stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProprError(f"stato competition {key} non valido") from exc
        if stamp.tzinfo is None:
            raise ProprError(f"stato competition {key} senza timezone")

    expected_assets = state.get("expected_assets")
    expected_sides = state.get("expected_sides")
    expected_quantities = state.get("expected_quantities")
    last_target = state.get("last_target")
    if not isinstance(expected_assets, list) or not isinstance(expected_sides, dict):
        raise ProprError("stato competition book atteso non valido")
    if not isinstance(expected_quantities, dict) or not isinstance(last_target, dict):
        raise ProprError("stato competition sizing atteso non valido")
    expected_keys = set(expected_sides)
    if expected_keys - set(SYMBOLS) or sorted(expected_assets) != sorted(expected_keys):
        raise ProprError("stato competition asset attesi incoerenti")
    if set(expected_quantities) != expected_keys or set(last_target) != expected_keys:
        raise ProprError("stato competition target/quantita' incompleti")
    if expected_keys and not state.get("last_rebalance_ts"):
        raise ProprError("stato competition book senza rebalance timestamp")
    target_gross = Decimal("0")
    for asset in expected_keys:
        side = expected_sides[asset]
        if side not in ("long", "short"):
            raise ProprError(f"stato competition lato non valido per {asset}")
        if _decimal(expected_quantities[asset], f"state quantity {asset}") <= 0:
            raise ProprError(f"stato competition quantity non positiva per {asset}")
        target = _decimal(last_target[asset], f"state target {asset}")
        if target == 0 or (target > 0) != (side == "long"):
            raise ProprError(f"stato competition target/lato incoerente per {asset}")
        target_gross += abs(target)
    gross_cap = EXPECTED_INITIAL_BALANCE * Decimal(str(GROSS))
    if target_gross > gross_cap + Decimal("1"):
        raise ProprError("stato competition gross target oltre cap")


def _write_state(state: dict) -> None:
    atomic_write_text(STATE_PATH, json.dumps(state, indent=1, sort_keys=True))


def _append_journal(event: dict) -> None:
    payload = {"ts": _now().isoformat(), "competition_id": COMPETITION_ID,
               "strategy": STRATEGY_ID, **event}
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, separators=(",", ":"), default=str) + "\n")


def _equity(account: dict) -> float:
    value = float(account["balance"]) + float(account.get("totalUnrealizedPnl", 0.0))
    if not math.isfinite(value) or value <= 0:
        raise ProprError(f"equity competition non valida: {value}")
    return value


def _initial_account_errors(account: dict) -> list[str]:
    errors = []
    balance = _decimal(account.get("balance"), "balance account iniziale")
    unrealized = _decimal(
        account.get("totalUnrealizedPnl", 0),
        "unrealized account iniziale",
    )
    if balance != EXPECTED_INITIAL_BALANCE:
        errors.append(f"balance={balance}")
    if unrealized != 0:
        errors.append(f"unrealized={unrealized}")
    return errors


def _due(state: dict, now: datetime) -> bool:
    raw = state.get("last_rebalance_ts")
    if not raw:
        return True
    try:
        last = datetime.fromisoformat(str(raw))
    except ValueError as exc:
        raise ProprError("last_rebalance_ts competition non valido") from exc
    if last.tzinfo is None:
        raise ProprError("last_rebalance_ts competition senza timezone")
    return now - last >= timedelta(hours=REBALANCE_H)


def _target(sizing_base: float) -> tuple[dict[str, float], dict[str, float]]:
    signals, prices = trailing_returns(list(SYMBOLS), LOOKBACK_H)
    observed = set(signals.index) & set(prices)
    if observed != set(SYMBOLS):
        missing = sorted(set(SYMBOLS) - observed)
        raise ProprError(f"segnali competition incompleti: {','.join(missing)}")
    weights = sign_weights(signals.reindex(SYMBOLS), gross=GROSS)
    for asset in SYMBOLS:
        _decimal(signals[asset], f"signal {asset}")
        _decimal(weights[asset], f"weight {asset}")
        if _decimal(prices[asset], f"price {asset}") <= 0:
            raise ProprError(f"price competition non positivo: {asset}")
    target = {asset: float(weights[asset]) * sizing_base
              for asset in SYMBOLS if abs(float(weights[asset])) > 1e-9}
    observed_prices = {asset: float(prices[asset]) for asset in SYMBOLS}
    _validate_target(target, observed_prices)
    return target, observed_prices


def _validate_target(target: dict, prices: dict) -> None:
    if not isinstance(target, dict) or not isinstance(prices, dict):
        raise ProprError("target competition non strutturato")
    if not target or len(target) > MAX_POSITIONS or set(target) - set(SYMBOLS):
        raise ProprError(f"target competition non valido: {len(target)} gambe")
    gross = Decimal("0")
    for asset, raw_target in target.items():
        notional = _decimal(raw_target, f"target {asset}")
        price = _decimal(prices.get(asset), f"price target {asset}")
        if notional == 0 or price <= 0:
            raise ProprError(f"target competition nullo/non prezzato: {asset}")
        gross += abs(notional)
    gross_cap = EXPECTED_INITIAL_BALANCE * Decimal(str(GROSS))
    if gross > gross_cap + Decimal("1"):
        raise ProprError(f"gross target competition oltre cap: {gross} > {gross_cap}")


def _looks_like_native_stop(order: dict) -> bool:
    return bool(
        order.get("type") == "stop_market"
        and order.get("reduceOnly") is True
        and order.get("closePosition") is True
        and order.get("positionId")
    )


def _cancel_orders(client: ProprClient, orders: list[dict], reason: str) -> None:
    if len(orders) > MAX_CANCELS:
        raise ProprError(f"cancellazioni competition oltre cap: {len(orders)}")
    actions = []
    for order in orders:
        order_id = str(order.get("orderId", ""))
        if not order_id:
            raise ProprError("ordine attivo competition senza orderId")
        response = client.cancel_order(order_id)
        if response.get("orderId") != order_id or response.get("status") != "cancelled":
            raise ProprError(f"cancellazione competition non verificabile: {order_id}")
        actions.append({"order_id": order_id, "reason": reason})
    if actions:
        _append_journal({"type": "cancel_orders", "actions": actions})


def _create_missing_stops(client: ProprClient, positions: list[dict]) -> list[dict]:
    active_orders = client.get_active_orders()
    keep_ids: set[str] = set()
    protected_position_ids: set[str] = set()
    for position in positions:
        plan = _stop_plan(position)
        planned_trigger = _decimal(plan["trigger_price"], "triggerPrice stop pianificato")
        if _stop_is_crossed(position, planned_trigger):
            raise ProprError(f"posizione oltre stop pianificato: {position['base']}")
        linked_stops = [
            order for order in active_orders
            if _looks_like_native_stop(order)
            and str(order.get("positionId", "")) == str(position["positionId"])
        ]
        for order in linked_stops:
            try:
                trigger = _decimal(order.get("triggerPrice"), "triggerPrice stop attivo")
            except ProprError:
                continue
            if _stop_is_crossed(position, trigger):
                raise ProprError(f"stop attivo gia' attraversato: {position['base']}")
        exact = sorted(
            (order for order in active_orders if _is_exact_protection(position, order)),
            key=lambda order: (str(order.get("createdAt", "")), str(order.get("orderId", ""))),
        )
        if exact:
            keep_ids.add(str(exact[0].get("orderId", "")))
            protected_position_ids.add(str(position["positionId"]))

    stale = []
    external = []
    for order in active_orders:
        if str(order.get("orderId", "")) in keep_ids:
            continue
        (stale if _looks_like_native_stop(order) else external).append(order)
    _cancel_orders(client, stale, "stale_or_duplicate_stop")
    if external:
        _cancel_orders(client, external, "unexpected_active_order")
        raise ProprError(f"ordini attivi esterni cancellati: {len(external)}")

    plans = [_stop_plan(position) for position in positions
             if str(position["positionId"]) not in protected_position_ids]
    if len(plans) > MAX_GUARD_CREATES:
        raise ProprError(f"guard competition oltre cap: {len(plans)}")
    actions = []
    for plan in plans:
        response = client.create_order(
            side=plan["side"], position_side=plan["position_side"],
            order_type="stop_market", asset=plan["asset"], quantity=plan["quantity"],
            reduce_only=True, close_position=True, intent_id=plan["intent_id"],
            position_id=plan["position_id"], trigger_price=plan["trigger_price"],
        )
        if (len(response) != 1 or response[0].get("intentId") != plan["intent_id"]
                or not response[0].get("orderId")
                or response[0].get("status") not in ("pending", "open", "partially_filled")):
            raise ProprError(f"stop competition non verificabile per {plan['asset']}")
        actions.append({"asset": plan["asset"], "order_id": response[0]["orderId"]})
    if actions:
        _append_journal({"type": "guard", "actions": actions})

    verified_orders = client.get_active_orders()
    for position in positions:
        exact = [order for order in verified_orders if _is_exact_protection(position, order)]
        if len(exact) != 1:
            raise ProprError(f"copertura stop non verificata per {position['base']}: {len(exact)}")
    unexpected = [
        order for order in verified_orders
        if not any(_is_exact_protection(position, order) for position in positions)
    ]
    if unexpected:
        raise ProprError(f"ordini attivi inattesi dopo guard: {len(unexpected)}")
    return actions


def _flatten_checked(client: ProprClient, positions: list[dict], reason: str) -> None:
    if not positions:
        return
    response_error = ""
    try:
        results = flatten(client, positions)
    except Exception as exc:  # l'ordine puo' aver eseguito anche dopo un timeout client
        results = [{"action": "transport_error", "error": f"{type(exc).__name__}: {exc}"}]
        response_error = f"transport {type(exc).__name__}"
    for result in results:
        response = result.get("resp")
        if result.get("action") == "error":
            response_error = f"ordine fallito {result.get('asset')}"
        elif (result.get("action") != "flatten" or not isinstance(response, list)
              or len(response) != 1 or not response[0].get("orderId")
              or response[0].get("status") not in
              ("pending", "open", "partially_filled", "filled")):
            response_error = f"risposta flatten non verificabile {result.get('asset')}"

    remaining: list[dict] = positions
    consecutive_flat = 0
    readback_error = ""
    for attempt in range(FLAT_READBACKS):
        try:
            remaining = client.get_positions()
        except Exception as exc:
            readback_error = f"{type(exc).__name__}: {exc}"
        else:
            readback_error = ""
            if not remaining:
                consecutive_flat += 1
                if consecutive_flat >= FLAT_CONFIRMATIONS:
                    break
            else:
                consecutive_flat = 0
        if attempt + 1 < FLAT_READBACKS:
            time.sleep(1)
    _append_journal({"type": "flatten", "reason": reason, "orders": results,
                     "remaining_positions": [p.get("base") for p in remaining]})
    if remaining or readback_error or consecutive_flat < FLAT_CONFIRMATIONS:
        detail = readback_error or ",".join(str(p.get("base")) for p in remaining)
        if not detail:
            detail = f"flat confermato solo {consecutive_flat} volte"
        raise ProprError(f"flatten competition non confermato: {detail}")
    if response_error:
        raise ProprError(f"flatten competition eseguito ma risposta invalida: {response_error}")


def _signed_notionals(positions: list[dict]) -> dict[str, float]:
    result: dict[str, float] = {}
    for position in positions:
        sign = 1.0 if position["positionSide"] == "long" else -1.0
        result[position["base"]] = result.get(position["base"], 0.0) + (
            sign * float(abs(_decimal(
                position.get("notionalValue"),
                f"notionalValue {position.get('base')}",
            )))
        )
    return result


def _reconcile_target(
    positions: list[dict],
    target: dict[str, float],
    *,
    rel_tol: float = RECONCILE_REL_TOL,
    abs_tol: float = RECONCILE_ABS_TOL,
) -> list[str]:
    observed = _signed_notionals(positions)
    errors = []
    for asset in sorted(set(observed) | set(target)):
        want = float(_decimal(target.get(asset, 0.0), f"target {asset}"))
        have = float(_decimal(observed.get(asset, 0.0), f"observed {asset}"))
        tolerance = max(abs_tol, abs(want) * rel_tol)
        if (want == 0) != (have == 0) or (want and have and want * have < 0):
            errors.append(f"{asset}:side")
        elif abs(have - want) > tolerance:
            errors.append(f"{asset}:notional({have:.2f}!={want:.2f})")
    return errors


def _rebalance_response_errors(results: list[dict]) -> list[str]:
    errors = []
    for result in results:
        if result.get("action") == "error":
            errors.append(f"{result.get('asset')}:error")
            continue
        response = result.get("resp")
        if (result.get("action") != "adjust" or not isinstance(response, list)
                or len(response) != 1 or not response[0].get("orderId")
                or response[0].get("status") not in
                ("pending", "open", "partially_filled", "filled")):
            errors.append(f"{result.get('asset')}:response")
    return errors


def _book_drift(state: dict, positions: list[dict]) -> bool:
    expected = state.get("expected_sides") or {}
    current = {str(position["base"]): str(position["positionSide"]) for position in positions}
    if current != expected:
        return True

    expected_quantities = state.get("expected_quantities") or {}
    current_quantities = {
        str(position["base"]): abs(_decimal(position.get("quantity"), "quantity runtime"))
        for position in positions
    }
    if set(current_quantities) != set(expected_quantities):
        return True
    for asset, expected_raw in expected_quantities.items():
        expected_quantity = abs(_decimal(expected_raw, f"expected quantity {asset}"))
        tolerance = max(Decimal("0.00000001"), expected_quantity * QUANTITY_REL_TOL)
        if abs(current_quantities[asset] - expected_quantity) > tolerance:
            return True

    if not expected:
        return False
    last_target = state.get("last_target") or {}
    if not last_target:
        return True
    return bool(_reconcile_target(
        positions,
        {asset: float(value) for asset, value in last_target.items()},
        rel_tol=RUNTIME_RECONCILE_REL_TOL,
        abs_tol=RUNTIME_RECONCILE_ABS_TOL,
    ))


def _write_status(*, mode: str, account_id: str, attempt: dict, account: dict,
                  positions: list[dict], state: dict | None = None, note: str = "") -> None:
    equity = _equity(account)
    payload = {
        "competition_id": COMPETITION_ID,
        "strategy": STRATEGY_ID,
        "mode": mode,
        "paper_only": True,
        "official_candidate": False,
        "account_id": account_id,
        "attempt_status": attempt.get("status"),
        "start_at": START_AT.isoformat(),
        "flatten_at": FLATTEN_AT.isoformat(),
        "end_at": END_AT.isoformat(),
        "balance": round(float(account["balance"]), 2),
        "equity": round(equity, 2),
        "gross": GROSS,
        "daily_stop_pct": DAILY_STOP_PCT,
        "total_stop_pct": TOTAL_STOP_PCT,
        "positions": [
            {"asset": position["base"], "side": position["positionSide"],
             "notional": round(float(position["notionalValue"]), 2),
             "unrealized_pnl": round(float(position.get("unrealizedPnl", 0.0)), 2)}
            for position in positions
        ],
        "state": state or {},
        "note": note,
        "updated_at": _now().isoformat(),
    }
    atomic_write_text(STATUS_PATH, json.dumps(payload, indent=1, sort_keys=True))


def _write_error_marker(message: str, state: dict | None = None) -> None:
    try:
        previous = json.loads(STATUS_PATH.read_text()) if STATUS_PATH.exists() else {}
    except (OSError, json.JSONDecodeError):
        previous = {}
    previous.update({
        "competition_id": COMPETITION_ID,
        "strategy": STRATEGY_ID,
        "mode": "error",
        "paper_only": True,
        "official_candidate": False,
        "note": message[:500],
        "state": state or previous.get("state", {}),
        "updated_at": _now().isoformat(),
    })
    atomic_write_text(STATUS_PATH, json.dumps(previous, indent=1, sort_keys=True))


def _roll_day(state: dict, positions: list[dict], equity: float, now: datetime) -> None:
    today = now.date().isoformat()
    if state.get("day_date") == today:
        return
    previous_equity = float(_decimal(state.get("last_equity", equity), "state last_equity"))
    state["day_date"] = today
    state["day_start_equity"] = round(max(equity, previous_equity), 8)
    if state.get("halted_today") and state.get("halt_kind") == "daily":
        if positions:
            _set_halt(state, "daily_rollover_residual", permanent=True)
            return
        state.update({"halted_today": False, "halt_kind": "", "halt_reason": "",
                      "last_rebalance_ts": "", "expected_assets": [],
                      "expected_sides": {}, "expected_quantities": {},
                      "last_target": {}})


def _set_halt(state: dict, reason: str, *, permanent: bool) -> None:
    state["halted_today"] = True
    state["halt_kind"] = "operational" if permanent else "daily"
    state["halt_reason"] = reason
    if permanent:
        state["permanently_halted"] = True


def _risk_reason(state: dict, positions: list[dict], equity: float, now: datetime) -> tuple[str, bool]:
    if now >= FLATTEN_AT:
        return ("scheduled_end_flatten" if now < END_AT else "competition_ended", True)
    if state.get("permanently_halted"):
        return (str(state.get("halt_reason") or "permanent_halt"), True)
    hwm = max(float(_decimal(state.get("high_water_mark", equity),
                             "state high_water_mark")), equity)
    state["high_water_mark"] = round(hwm, 8)
    static_floor = float(EXPECTED_INITIAL_BALANCE) * (1.0 - TOTAL_STOP_PCT)
    hwm_floor = hwm - float(EXPECTED_INITIAL_BALANCE) * TOTAL_STOP_PCT
    if equity <= max(static_floor, hwm_floor):
        return ("total_stop", True)
    day_start = float(_decimal(state.get("day_start_equity"), "state day_start_equity"))
    if equity - day_start <= -float(EXPECTED_INITIAL_BALANCE) * DAILY_STOP_PCT:
        return ("daily_stop", False)
    if state.get("halted_today"):
        return (str(state.get("halt_reason") or "daily_halt"),
                state.get("halt_kind") != "daily")
    if _book_drift(state, positions):
        return ("native_stop_or_external_drift", True)
    return ("", False)


def _cancel_all_active_orders(client: ProprClient, reason: str) -> None:
    active = client.get_active_orders()
    _cancel_orders(client, active, reason)
    if client.get_active_orders():
        raise ProprError("ordini attivi residui dopo cancellazione")


def _flatten_and_cleanup(client: ProprClient, positions: list[dict], reason: str) -> None:
    _flatten_checked(client, positions, reason)
    _cancel_all_active_orders(client, f"{reason}_cleanup")
    remaining = client.get_positions()
    if remaining:
        raise ProprError("book competition riapparso dopo cleanup")


def _recover_after_write(client: ProprClient, state: dict, now: datetime,
                         reason: str, error: Exception) -> None:
    _set_halt(state, reason, permanent=True)
    state.update({"expected_assets": [], "expected_sides": {}, "expected_quantities": {},
                  "last_target": {}, "last_manage_ts": now.isoformat()})
    recovery_errors = []
    recovered = False
    for attempt in range(1, RECOVERY_ATTEMPTS + 1):
        try:
            positions = client.get_positions()
        except Exception as exc:
            recovery_errors.append(
                f"readback[{attempt}]={type(exc).__name__}:{exc}"
            )
            if attempt < RECOVERY_ATTEMPTS:
                time.sleep(1)
            continue
        try:
            _create_missing_stops(client, positions)
        except Exception as exc:
            recovery_errors.append(f"guard[{attempt}]={type(exc).__name__}:{exc}")
        try:
            _flatten_and_cleanup(client, positions, reason)
        except Exception as exc:
            recovery_errors.append(f"flatten[{attempt}]={type(exc).__name__}:{exc}")
        else:
            recovered = True
            break
        if attempt < RECOVERY_ATTEMPTS:
            time.sleep(1)
    try:
        state["last_equity"] = round(_equity(client.get_account()), 8)
    except Exception as exc:
        recovery_errors.append(f"account={type(exc).__name__}:{exc}")
    _write_state(state)
    detail = "; ".join(recovery_errors)
    if recovered:
        detail = f"{detail}; recovery verified flat" if detail else "recovery verified flat"
    elif not detail:
        detail = "recovery non verificata"
    message = f"{reason}: {type(error).__name__}: {error}; {detail}"
    _write_error_marker(message, state)
    raise ProprError(message) from error


def _runtime_book_errors(state: dict, positions: list[dict], orders: list[dict]) -> list[str]:
    errors = []
    if _book_drift(state, positions):
        errors.append("book side/assets diverge dallo stato")
    for position in positions:
        count = sum(_is_exact_protection(position, order) for order in orders)
        if count != 1:
            errors.append(f"{position['base']}:stop_count={count}")
    for order in orders:
        if not any(_is_exact_protection(position, order) for position in positions):
            errors.append(f"ordine_inatteso={order.get('orderId')}")
    return errors


def check() -> dict:
    """Preflight read-only: account pin, attempt, balance e posizioni."""
    if _automanage_enabled() and not _guard_enabled():
        raise ProprError("automanage competition richiede guard competition attivo")
    account_id = _account_id()
    client = ProprClient(read_only=True)
    client.setup(
        expected_account_id=account_id,
        expected_competition_id=COMPETITION_ID,
        expected_competition_slug=COMPETITION_SLUG,
    )
    attempt = client.active_attempt
    _validate_attempt(attempt, account_id)
    positions = client.get_positions()
    _validate_positions(positions)
    account = client.get_account()
    active_orders = client.get_active_orders()
    state = _read_state()
    if not state:
        initial_errors = _initial_account_errors(account)
        if positions or active_orders or initial_errors:
            detail = ",".join(initial_errors) or "book_or_orders_nonflat"
            raise ProprError(f"prima attivazione account non vergine: {detail}")
    else:
        _validate_state(state, account_id)
        errors = _runtime_book_errors(state, positions, active_orders)
        if errors:
            raise ProprError("preflight runtime: " + "; ".join(errors))
    result = {
        "mode": "check",
        "account_id": account_id,
        "competition_id": COMPETITION_ID,
        "equity": round(_equity(account), 2),
        "positions": len(positions),
        "active_orders": len(active_orders),
        "writes": 0,
    }
    _write_status(mode="check", account_id=account_id, attempt=attempt,
                  account=account, positions=positions, state=state,
                  note="preflight API read-only; status locale aggiornato")
    print(json.dumps(result, indent=2))
    return result


def guard() -> dict:
    """Crea soltanto protezioni reduce-only sulle posizioni gia' aperte."""
    if not _guard_enabled():
        print("competition guard disabilitato dal kill switch")
        return {"mode": "guard_disabled", "writes": 0}
    now = _now()
    if now < START_AT:
        print(f"competition non iniziata; guard in attesa fino a {START_AT.isoformat()}")
        return {"mode": "waiting", "writes": 0}
    account_id = _account_id()
    client = ProprClient(read_only=False)
    client.setup(
        expected_account_id=account_id,
        expected_competition_id=COMPETITION_ID,
        expected_competition_slug=COMPETITION_SLUG,
    )
    attempt = client.active_attempt
    _validate_attempt(attempt, account_id)
    positions = client.get_positions()
    account = client.get_account()
    equity = _equity(account)
    active_orders = client.get_active_orders()
    try:
        state = _read_state()
        if state:
            _validate_state(state, account_id)
    except Exception as exc:
        state = _fresh_state(account_id, equity, now)
        _recover_after_write(client, state, now, "state_unreadable", exc)
    if not state:
        state = _fresh_state(account_id, equity, now)
        _write_state(state)
        initial_errors = _initial_account_errors(account)
        if positions or active_orders or initial_errors:
            _recover_after_write(
                client,
                state,
                now,
                "first_activation_nonflat",
                ProprError(
                    "prima attivazione guard non vergine: "
                    + (",".join(initial_errors) or "book_or_orders_nonflat")
                ),
            )
        _write_status(mode="guard", account_id=account_id, attempt=attempt,
                      account=account, positions=[], state=state,
                      note="ready; nessuna esposizione")
        result = {"mode": "guard", "created": 0, "positions": 0}
        print(json.dumps(result, indent=2))
        return result
    try:
        _validate_positions(positions)
        _roll_day(state, positions, equity, now)
        reason, permanent = _risk_reason(state, positions, equity, now)
    except Exception as exc:
        _recover_after_write(client, state, now, "state_or_position_invalid", exc)
    if reason:
        _set_halt(state, reason, permanent=permanent)
        try:
            _flatten_and_cleanup(client, positions, reason)
        except Exception as exc:
            _recover_after_write(client, state, now, f"{reason}_recovery", exc)
        state.update({"expected_assets": [], "expected_sides": {}, "expected_quantities": {},
                      "last_target": {}, "last_manage_ts": now.isoformat()})
        account = client.get_account()
        state["last_equity"] = round(_equity(account), 8)
        _write_state(state)
        _write_status(mode="halted", account_id=account_id, attempt=attempt,
                      account=account, positions=[], state=state, note=reason)
        result = {"mode": "halted", "reason": reason, "positions": 0}
        print(json.dumps(result, indent=2))
        if reason not in ("scheduled_end_flatten", "competition_ended"):
            raise ProprError(f"competition halted: {reason}")
        return result
    try:
        actions = _create_missing_stops(client, positions)
    except Exception as exc:
        _recover_after_write(client, state, now, "guard_failure", exc)
    account = client.get_account()
    state["last_equity"] = round(_equity(account), 8)
    state["last_manage_ts"] = now.isoformat()
    _write_state(state)
    _write_status(mode="guard", account_id=account_id, attempt=attempt,
                  account=account, positions=client.get_positions(), state=state,
                  note="guard-only")
    result = {"mode": "guard", "created": len(actions), "positions": len(positions)}
    print(json.dumps(result, indent=2))
    return result


def manage() -> dict:
    """Gestione deterministica; nessuna rete se kill switch o tempo la bloccano."""
    if not _automanage_enabled():
        print("competition automanage disabilitato dal kill switch")
        return {"mode": "disabled", "writes": 0}
    if not _guard_enabled():
        raise ProprError("automanage competition bloccato: guard competition disabilitato")
    now = _now()
    if now < START_AT:
        print(f"competition non iniziata; attesa fino a {START_AT.isoformat()}")
        return {"mode": "waiting", "writes": 0}

    account_id = _account_id()
    client = ProprClient(read_only=False)
    client.setup(
        expected_account_id=account_id,
        expected_competition_id=COMPETITION_ID,
        expected_competition_slug=COMPETITION_SLUG,
    )
    attempt = client.active_attempt
    _validate_attempt(attempt, account_id)
    positions = client.get_positions()
    account = client.get_account()
    equity = _equity(account)

    active_orders = client.get_active_orders()
    try:
        state = _read_state()
        if state:
            _validate_state(state, account_id)
    except Exception as exc:
        state = _fresh_state(account_id, equity, now)
        _recover_after_write(client, state, now, "state_unreadable", exc)
    if not state:
        state = _fresh_state(account_id, equity, now)
        _write_state(state)
        initial_errors = _initial_account_errors(account)
        if positions or active_orders or initial_errors:
            _recover_after_write(
                client,
                state,
                now,
                "first_activation_nonflat",
                ProprError(
                    "prima attivazione manage non vergine: "
                    + (",".join(initial_errors) or "book_or_orders_nonflat")
                ),
            )
    try:
        _validate_positions(positions)
        _roll_day(state, positions, equity, now)
        reason, permanent = _risk_reason(state, positions, equity, now)
    except Exception as exc:
        _recover_after_write(client, state, now, "state_or_position_invalid", exc)

    if reason:
        _set_halt(state, reason, permanent=permanent)
        try:
            _flatten_and_cleanup(client, positions, reason)
        except Exception as exc:
            _recover_after_write(client, state, now, f"{reason}_recovery", exc)
        positions = []
        state["expected_assets"] = []
        state["expected_sides"] = {}
        state["expected_quantities"] = {}
        state["last_target"] = {}
        state["last_manage_ts"] = now.isoformat()
        account = client.get_account()
        state["last_equity"] = round(_equity(account), 8)
        _write_state(state)
        _write_status(mode="halted", account_id=account_id, attempt=attempt,
                      account=account, positions=positions, state=state, note=reason)
        result = {"mode": "halted", "reason": reason, "positions": len(positions)}
        print(json.dumps(result, indent=2))
        return result

    # Pre-guard obbligatorio: una run non cambia il book se l'esposizione gia'
    # presente non puo' essere resa server-side protected.
    try:
        _create_missing_stops(client, positions)
    except Exception as exc:
        _recover_after_write(client, state, now, "pre_guard_failure", exc)

    action = "guard_only"
    try:
        rebalance_due = _due(state, now)
    except Exception as exc:
        _recover_after_write(client, state, now, "state_or_position_invalid", exc)
    if rebalance_due:
        try:
            target, prices = _target(float(EXPECTED_INITIAL_BALANCE))
            _validate_target(target, prices)
            orders = rebalance(client, target, prices, positions)
            _append_journal({"type": "rebalance", "target": target, "orders": orders})
            positions = client.get_positions()
            _validate_positions(positions)
            # Post-guard prima di valutare un eventuale errore parziale: ogni
            # write riuscita deve essere protetta o immediatamente appiattita.
            _create_missing_stops(client, positions)
            failures = _rebalance_response_errors(orders) + _reconcile_target(positions, target)
            if failures:
                raise ProprError("partial_rebalance: " + ",".join(failures))
        except Exception as exc:
            _recover_after_write(client, state, now, "rebalance_recovery", exc)
        state["last_rebalance_ts"] = now.isoformat()
        state["last_target"] = {asset: round(value, 2) for asset, value in target.items()}
        state["expected_assets"] = sorted(target)
        state["expected_sides"] = {
            asset: "long" if value > 0 else "short" for asset, value in target.items()
        }
        state["expected_quantities"] = {
            str(position["base"]): format(
                abs(_decimal(position.get("quantity"), "quantity post-rebalance")),
                "f",
            )
            for position in positions
        }
        action = "rebalance"

    state["last_manage_ts"] = now.isoformat()
    account = client.get_account()
    state["last_equity"] = round(_equity(account), 8)
    state["high_water_mark"] = round(max(
        float(_decimal(state.get("high_water_mark", equity), "state high_water_mark")),
        float(_decimal(state["last_equity"], "state last_equity")),
    ), 8)
    _write_state(state)
    _write_status(mode="manage", account_id=account_id, attempt=attempt,
                  account=account, positions=positions, state=state, note=action)
    result = {"mode": "manage", "action": action, "positions": len(positions),
              "equity": round(_equity(account), 2)}
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="preflight API read-only")
    mode.add_argument("--guard", action="store_true", help="solo stop reduce-only")
    mode.add_argument("--manage", action="store_true", help="gestione competition gated")
    args = parser.parse_args()
    try:
        if args.check:
            check()
        elif args.guard:
            guard()
        else:
            manage()
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _write_error_marker(message)
        parser.exit(2, f"competition runner bloccato: {message}\n")


if __name__ == "__main__":
    main()
