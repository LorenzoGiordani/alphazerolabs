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
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from scripts.propr_client import ProprClient, ProprError


ROOT = Path(__file__).resolve().parent.parent
JOURNAL = ROOT / "paper/propr_guard_journal.jsonl"
EXPECTED_CHALLENGE_SLUG = "free-trial"
EXPECTED_INITIAL_BALANCE = Decimal("5000")
STOP_DISTANCE = Decimal("0.04")
MAX_CREATES = 8
GUARD_VERSION = "propr-guard-v1"
_FALLBACK_ULID_MS = 1_577_836_800_000  # 2020-01-01 UTC; stable if API omits createdAt.
_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


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


def _intent_id(position: dict, quantity: str, trigger_price: str) -> str:
    seed = "|".join((
        GUARD_VERSION,
        str(position["positionId"]),
        quantity,
        trigger_price,
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
    if balance != EXPECTED_INITIAL_BALANCE:
        raise ProprError(f"balance iniziale inatteso: {balance}")


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
        protected = any(
            order.get("type") == "stop_market"
            and str(order.get("positionId", "")) == position_id
            and str(order.get("side", "")).lower() == closing_side
            and str(order.get("positionSide", "")).lower() == position_side
            and order.get("reduceOnly") is True
            and order.get("closePosition") is True
            for order in open_orders
        )
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
            "position_side": position_side,
            "quantity": quantity,
            "trigger_price": trigger_price,
            "intent_id": _intent_id(position, quantity, trigger_price),
        })
    return plans[:MAX_CREATES], skipped_existing


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


def main(*, execute: bool = False) -> dict:
    expected_account_id = os.environ.get("PROPR_EXPECTED_ACCOUNT_ID", "").strip()
    if execute and not _enabled("PROPR_GUARD_ENABLED"):
        raise ProprError("guard disabilitato: PROPR_GUARD_ENABLED deve essere true")
    if execute and not expected_account_id:
        raise ProprError("PROPR_EXPECTED_ACCOUNT_ID obbligatorio con --execute")

    canary = os.environ.get("PROPR_GUARD_CANARY_ASSET", "*").strip().upper() or "*"
    client = ProprClient(read_only=not execute)
    account_id = client.setup(
        expected_account_id=expected_account_id or None,
        expected_challenge_slug=EXPECTED_CHALLENGE_SLUG,
    )
    _validate_attempt(client.active_attempt, expected_account_id or None)
    positions = client.get_positions()
    open_orders = client.get_orders(status="open")
    plans, skipped_existing = _build_plan(positions, open_orders, canary)

    actions: list[dict] = []
    if execute:
        for plan in plans:
            action = plan.copy()
            try:
                client.create_order(
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
            except ProprError:
                _append_journal(account_id, actions, status="partial_error")
                raise
            actions.append(action)
        _append_journal(account_id, actions, status="created")

    result = {
        "mode": "execute" if execute else "plan",
        "account_id": account_id,
        "challenge": EXPECTED_CHALLENGE_SLUG,
        "initial_balance": float(EXPECTED_INITIAL_BALANCE),
        "canary": canary,
        "stop_distance_pct": float(STOP_DISTANCE * 100),
        "planned_count": len(plans),
        "skipped_existing": skipped_existing,
        "plans": plans,
        "created_count": len(actions),
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="crea gli stop nativi pianificati")
    args = parser.parse_args()
    try:
        main(execute=args.execute)
    except ProprError as exc:
        parser.exit(2, f"propr guard bloccato: {exc}\n")
