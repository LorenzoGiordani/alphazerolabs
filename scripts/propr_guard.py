"""Protezione nativa per il solo account Propr Free Trial paper da 5.000 USD.

Senza ``--execute`` calcola il piano con un client read-only. L'esecuzione
richiede due pin espliciti in env e non apre mai nuova esposizione: crea solo
stop-market reduce-only/close-position sulle posizioni gia aperte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.evidence import verify_propr_paper_evidence
from backtest.strategy import load
from scripts.propr_client import ProprClient, ProprError
from scripts.propr_contract import (
    EXPECTED_CHALLENGE_SLUG,
    EXPECTED_INITIAL_BALANCE,
    GUARD_MAX_CREATES,
    GUARD_STOP_DISTANCE,
    GUARD_VERSION,
    RULEBOOK,
    SPEC_REL,
    execution_contract,
)


JOURNAL = ROOT / "paper/propr_guard_journal.jsonl"
EXPECTED_RULES = {
    "profitTargetPercent": Decimal(str(RULEBOOK["profit_target_pct"])),
    "maxDailyLossPercent": Decimal(str(RULEBOOK["max_daily_loss_pct"])),
    "maxDrawdownPercent": Decimal(str(RULEBOOK["max_drawdown_pct"])),
}
STOP_DISTANCE = Decimal(str(GUARD_STOP_DISTANCE))
MAX_CREATES = GUARD_MAX_CREATES
_FALLBACK_ULID_MS = 1_577_836_800_000  # 2020-01-01 UTC; stable if API omits createdAt.
_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


def _require_write_evidence(expected_account_id: str) -> dict:
    spec = load(ROOT / SPEC_REL)
    evidence = verify_propr_paper_evidence(
        spec,
        ROOT,
        account_id=expected_account_id,
        execution_contract=execution_contract(spec),
    )
    if not evidence["verified"]:
        raise ProprError(
            "evidenza paper non verificata: " + ", ".join(evidence["reasons"])
        )
    return evidence


def _parse_decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProprError(f"{field} non valido: {value}") from exc
    if not parsed.is_finite():
        raise ProprError(f"{field} non finito: {value}")
    return parsed


def _five_significant(value: Decimal) -> str:
    if value <= 0:
        raise ProprError(f"trigger price non valido: {value}")
    quantum = Decimal(1).scaleb(value.adjusted() - 4)
    rounded = value.quantize(quantum)
    rendered = format(rounded, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _ulid_from_bytes(value: bytes) -> str:
    if len(value) != 16:
        raise ValueError("un ULID richiede 16 byte")
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


def _intent_id(position: dict) -> str:
    seed = "|".join((
        GUARD_VERSION,
        str(position["positionId"]),
        str(position["positionSide"]).lower(),
    )).encode()
    randomness = hashlib.sha256(seed).digest()[:10]
    value = _created_at_ms(position).to_bytes(6, "big") + randomness
    return _ulid_from_bytes(value)


def _validate_attempt(attempt: dict | None, expected_account_id: str | None) -> None:
    if not attempt:
        raise ProprError("challenge attempt attiva assente")
    if attempt.get("status") != "active":
        raise ProprError(f"challenge non attiva: {attempt.get('status')}")
    if expected_account_id and attempt.get("accountId") != expected_account_id:
        raise ProprError(f"account inatteso: {attempt.get('accountId')}")
    challenge = attempt.get("challenge", {})
    if challenge.get("slug") != EXPECTED_CHALLENGE_SLUG:
        raise ProprError(f"challenge inattesa: {challenge.get('slug')}")
    balance = _parse_decimal(challenge.get("initialBalance"), "initialBalance")
    if balance != Decimal(str(EXPECTED_INITIAL_BALANCE)):
        raise ProprError(f"balance iniziale inatteso: {balance}")
    phases = challenge.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ProprError("regole challenge assenti")
    phase = phases[0]
    for field, expected in EXPECTED_RULES.items():
        observed = _parse_decimal(phase.get(field), field)
        if observed != expected:
            raise ProprError(f"{field} inatteso: {observed}")


def _is_protective_order(position: dict, order: dict) -> bool:
    position_side = str(position.get("positionSide", "")).lower()
    closing_side = "sell" if position_side == "long" else "buy" if position_side == "short" else ""
    order_position_side = "long" if closing_side == "buy" else "short" if closing_side else ""
    return bool(
        order.get("type") == "stop_market"
        and str(order.get("positionId", "")) == str(position.get("positionId", ""))
        and str(order.get("side", "")).lower() == closing_side
        and str(order.get("positionSide", "")).lower() == order_position_side
        and order.get("reduceOnly") is True
        and order.get("closePosition") is True
    )


def reconciliation_summary(positions: list[dict], active_orders: list[dict]) -> dict:
    position_ids = [str(position.get("positionId", "")) for position in positions]
    unique_positions = (
        all(position_ids)
        and len(position_ids) == len(set(position_ids))
    )
    position_by_id = {
        str(position["positionId"]): position
        for position in positions
        if position.get("positionId")
    }
    counts = {position_id: 0 for position_id in position_by_id}
    unmatched = 0
    protective_orders = 0
    unexpected_orders = 0
    for order in active_orders:
        if not (
            order.get("type") == "stop_market"
            and order.get("reduceOnly") is True
            and order.get("closePosition") is True
        ):
            unexpected_orders += 1
            continue
        protective_orders += 1
        position = position_by_id.get(str(order.get("positionId", "")))
        if position and _is_protective_order(position, order):
            counts[str(position["positionId"])] += 1
        else:
            unmatched += 1
    protected = sum(count > 0 for count in counts.values())
    duplicates = sum(max(0, count - 1) for count in counts.values())
    prewrite_safe = (
        unique_positions
        and duplicates == 0
        and unmatched == 0
        and unexpected_orders == 0
    )
    exact = (
        prewrite_safe
        and all(count == 1 for count in counts.values())
    )
    return {
        "open_positions": len(position_by_id),
        "active_protective_orders": protective_orders,
        "protected_positions": protected,
        "duplicate_protective_orders": duplicates,
        "unmatched_protective_orders": unmatched,
        "unexpected_active_orders": unexpected_orders,
        "prewrite_safe": prewrite_safe,
        "fully_protected": unique_positions and protected == len(position_by_id),
        "exactly_one_per_position": exact,
    }


def _build_plan(positions: list[dict], open_orders: list[dict], canary: str) -> tuple[list[dict], int]:
    plans: list[dict] = []
    skipped_existing = 0
    selected = sorted(
        positions,
        key=lambda p: (str(p.get("base", "")), str(p.get("positionId", ""))),
    )
    for position in selected:
        asset = str(position.get("base", "")).upper()
        if canary not in ("", "*") and asset != canary:
            continue
        position_id = str(position.get("positionId", ""))
        if not asset or not position_id:
            raise ProprError("posizione senza base o positionId")
        position_side = str(position.get("positionSide", "")).lower()
        if position_side not in ("long", "short"):
            raise ProprError(f"positionSide inatteso per {asset}: {position_side}")
        closing_side = "sell" if position_side == "long" else "buy"
        # L'API live (code 13096, 2026-07-17) impone buy+long / sell+short
        # anche per un close condizionale, diversamente dall'esempio nei docs.
        order_position_side = "long" if closing_side == "buy" else "short"
        protected = any(_is_protective_order(position, order) for order in open_orders)
        if protected:
            skipped_existing += 1
            continue
        quantity_value = abs(_parse_decimal(position.get("quantity"), f"quantity {asset}"))
        if quantity_value == 0:
            continue
        quantity = format(quantity_value, "f")
        mark = _parse_decimal(position.get("markPrice"), f"markPrice {asset}")
        multiplier = Decimal("1") - STOP_DISTANCE if position_side == "long" else Decimal("1") + STOP_DISTANCE
        trigger_price = _five_significant(mark * multiplier)
        plans.append({
            "asset": asset,
            "position_id": position_id,
            "side": closing_side,
            "position_side": order_position_side,
            "quantity": quantity,
            "trigger_price": trigger_price,
            "intent_id": _intent_id(position),
        })
    if len(plans) > MAX_CREATES:
        raise ProprError(f"guard rifiutato: {len(plans)} stop > cap {MAX_CREATES}")
    return plans, skipped_existing


def _build_dedupe_plan(positions: list[dict], active_orders: list[dict]) -> list[dict]:
    duplicates: list[dict] = []
    for position in sorted(positions, key=lambda p: str(p.get("positionId", ""))):
        matching = [order for order in active_orders if _is_protective_order(position, order)]
        if len(matching) < 2:
            continue
        if any(not order.get("createdAt") for order in matching):
            raise ProprError(f"stop senza createdAt per {position.get('base')}")
        matching.sort(key=lambda order: (str(order["createdAt"]), str(order["orderId"])))
        keep = matching[0]
        for order in matching[1:]:
            duplicates.append({
                "asset": str(position.get("base", "")),
                "position_id": str(position["positionId"]),
                "order_id": str(order["orderId"]),
                "intent_id": str(order.get("intentId", "")),
                "created_at": str(order["createdAt"]),
                "kept_order_id": str(keep["orderId"]),
            })
    return duplicates


def _append_journal(account_id: str, actions: list[dict], *, status: str) -> None:
    if not actions:
        return
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "propr_guard",
        "version": GUARD_VERSION,
        "account_id": account_id,
        "status": status,
        "actions": actions,
    }
    with open(JOURNAL, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, separators=(",", ":")) + "\n")


def dedupe(*, expected_duplicates: int) -> dict:
    if not _enabled("PROPR_DEDUPE_ENABLED"):
        raise ProprError("dedupe disabilitato: PROPR_DEDUPE_ENABLED deve essere true")
    if _enabled("PROPR_GUARD_ENABLED") or _enabled("PROPR_AUTOMANAGE_ENABLED"):
        raise ProprError("dedupe richiede guard e automanage disattivati")
    if expected_duplicates < 1 or expected_duplicates > MAX_CREATES:
        raise ProprError(f"expected_duplicates fuori cap: {expected_duplicates}")
    expected_account_id = os.environ.get("PROPR_EXPECTED_ACCOUNT_ID", "").strip()
    if not expected_account_id:
        raise ProprError("PROPR_EXPECTED_ACCOUNT_ID obbligatorio con --dedupe")
    _require_write_evidence(expected_account_id)

    client = ProprClient(read_only=False)
    account_id = client.setup(
        expected_account_id=expected_account_id,
        expected_challenge_slug=EXPECTED_CHALLENGE_SLUG,
    )
    _validate_attempt(client.active_attempt, expected_account_id)
    duplicates = _build_dedupe_plan(client.get_positions(), client.get_active_orders())
    if len(duplicates) != expected_duplicates:
        raise ProprError(
            f"dedupe rifiutato: attesi {expected_duplicates}, trovati {len(duplicates)}"
        )

    actions: list[dict] = []
    for duplicate in duplicates:
        response = client.cancel_order(duplicate["order_id"])
        if (response.get("orderId") != duplicate["order_id"]
                or response.get("status") != "cancelled"):
            _append_journal(account_id, actions, status="dedupe_partial_error")
            raise ProprError(f"cancellazione non verificabile per {duplicate['order_id']}")
        actions.append(duplicate)
    _append_journal(account_id, actions, status="deduped")
    result = {
        "mode": "dedupe",
        "account_id": account_id,
        "expected_duplicates": expected_duplicates,
        "cancelled_count": len(actions),
        "actions": actions,
    }
    print(json.dumps(result, indent=2))
    return result


def main(*, execute: bool = False) -> dict:
    expected_account_id = os.environ.get("PROPR_EXPECTED_ACCOUNT_ID", "").strip()
    if execute and not _enabled("PROPR_GUARD_ENABLED"):
        raise ProprError("guard disabilitato: PROPR_GUARD_ENABLED deve essere true")
    if execute and not expected_account_id:
        raise ProprError("PROPR_EXPECTED_ACCOUNT_ID obbligatorio con --execute")
    if execute:
        _require_write_evidence(expected_account_id)

    canary = os.environ.get("PROPR_GUARD_CANARY_ASSET", "*").strip().upper() or "*"
    client = ProprClient(read_only=not execute)
    account_id = client.setup(
        expected_account_id=expected_account_id or None,
        expected_challenge_slug=EXPECTED_CHALLENGE_SLUG,
    )
    _validate_attempt(client.active_attempt, expected_account_id or None)
    positions = client.get_positions()
    active_orders = client.get_active_orders()
    plans, skipped_existing = _build_plan(positions, active_orders, canary)
    reconciliation = reconciliation_summary(positions, active_orders)

    actions: list[dict] = []
    if execute:
        if not reconciliation["prewrite_safe"]:
            raise ProprError(
                "preflight stop non sicuro: "
                f"duplicates={reconciliation['duplicate_protective_orders']} "
                f"unmatched={reconciliation['unmatched_protective_orders']} "
                f"unexpected={reconciliation['unexpected_active_orders']}"
            )
        for plan in plans:
            action = plan.copy()
            try:
                response = client.create_order(
                    side=plan["side"],
                    position_side=plan["position_side"],
                    order_type="stop_market",
                    asset=plan["asset"],
                    quantity=plan["quantity"],
                    reduce_only=True,
                    close_position=True,
                    intent_id=plan["intent_id"],
                    position_id=plan["position_id"],
                    trigger_price=plan["trigger_price"],
                )
                if (len(response) != 1
                        or response[0].get("intentId") != plan["intent_id"]
                        or not response[0].get("orderId")
                        or response[0].get("status") not in ("pending", "open", "partially_filled")):
                    raise ProprError(f"risposta creazione stop non verificabile per {plan['asset']}")
            except ProprError:
                _append_journal(account_id, actions, status="partial_error")
                raise
            action["order_id"] = response[0]["orderId"]
            actions.append(action)
        _append_journal(account_id, actions, status="created")
        reconciliation = reconciliation_summary(
            client.get_positions(),
            client.get_active_orders(),
        )
        if not reconciliation["exactly_one_per_position"]:
            _append_journal(account_id, actions, status="reconciliation_failed")
            raise ProprError(
                "riconciliazione stop non esatta: "
                f"positions={reconciliation['open_positions']} "
                f"orders={reconciliation['active_protective_orders']} "
                f"duplicates={reconciliation['duplicate_protective_orders']} "
                f"unmatched={reconciliation['unmatched_protective_orders']} "
                f"unexpected={reconciliation['unexpected_active_orders']}"
            )

    result = {
        "mode": "execute" if execute else "plan",
        "account_id": account_id,
        "challenge": EXPECTED_CHALLENGE_SLUG,
        "initial_balance": float(EXPECTED_INITIAL_BALANCE),
        "canary": canary,
        "stop_distance_pct": float(STOP_DISTANCE * 100),
        "planned_count": len(plans),
        "skipped_existing": skipped_existing,
        "reconciliation": reconciliation,
        "plans": plans,
        "created_count": len(actions),
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="crea gli stop nativi pianificati")
    mode.add_argument("--dedupe", action="store_true", help="cancella stop nativi duplicati")
    parser.add_argument("--expected-duplicates", type=int, default=0)
    args = parser.parse_args()
    try:
        if args.dedupe:
            dedupe(expected_duplicates=args.expected_duplicates)
        else:
            main(execute=args.execute)
    except ProprError as exc:
        parser.exit(2, f"propr guard bloccato: {exc}\n")
