"""Esegue una champion paper verificata sull'account virtuale Propr.

A differenza di portfolio_paper.py (ledger interno finto) qui gli ordini sono
REALI sull'account Free Trial di Propr (app.propr.xyz): tipo `paper` lato loro,
capitale virtuale ma esecuzione/enforcement (drawdown, daily loss, profit
target) vero e verificabile via API. Serve a validare se la strategia già
promossa a champion nel loop interno avrebbe superato la challenge Propr.

Riusa la stessa logica di segnale di portfolio_paper.py (trailing_returns
multi-orizzonte + xs_momentum_weights) per restare fedele allo spec.

Uso: uv run scripts/propr_paper.py
"""
import json
import math
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.evidence import verify_evidence, verify_propr_paper_evidence
from backtest.portfolio import xs_momentum_weights
from backtest.strategy import load
from pipeline.live import atomic_write_text
from scripts.portfolio_paper import trailing_returns
from scripts.propr_client import ProprClient, ProprError
from scripts.propr_contract import (
    AUTOMANAGE_VERSION,
    EXPECTED_CHALLENGE_SLUG,
    EXPECTED_INITIAL_BALANCE,
    MAX_ORDERS_PER_ACTION,
    PROPR_DAILY_STOP_PCT,
    PROPR_GROSS_OVERRIDE,
    PROPR_TRANCHE_H,
    RULEBOOK,
    SPEC_REL,
    execution_contract,
)
from scripts.propr_guard import reconciliation_summary

SPEC_PATH = ROOT / SPEC_REL
JOURNAL = ROOT / "paper/propr_journal.jsonl"
STATUS_PATH = ROOT / "paper/propr_status.json"
STATE_PATH = ROOT / "paper/propr_state.json"

def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


def _paper_execution_contract(spec: dict) -> dict:
    return execution_contract(spec)


def _read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _fresh_management_state(equity: float, now: datetime) -> dict:
    """Non riusa target o tranche prodotti prima dell'autorizzazione esplicita."""
    return {
        "management_mode": AUTOMANAGE_VERSION,
        "activated_at": now.isoformat(),
        "day_date": now.date().isoformat(),
        "day_start_equity": equity,
        "halted_today": False,
    }


def _validate_target(
    target: dict,
    symbols: list[str],
    sizing_base: float,
    *,
    gross_cap: float = PROPR_GROSS_OVERRIDE,
) -> dict[str, float]:
    if not isinstance(target, dict):
        raise ProprError("target Propr non valido")
    allowed = set(symbols)
    normalized: dict[str, float] = {}
    for asset, value in target.items():
        if not isinstance(asset, str) or asset not in allowed or isinstance(value, bool):
            raise ProprError(f"target Propr non valido per {asset!r}")
        try:
            notional = float(value)
        except (TypeError, ValueError) as exc:
            raise ProprError(f"target Propr non valido per {asset}") from exc
        if not math.isfinite(notional):
            raise ProprError(f"target Propr non finito per {asset}")
        normalized[asset] = notional
    gross = sum(abs(value) for value in normalized.values())
    if gross > sizing_base * gross_cap + 0.10:
        raise ProprError(f"target Propr oltre gross cap: {gross:.2f}")
    if abs(sum(normalized.values())) > 0.10:
        raise ProprError("target Propr non dollar-neutral")
    return normalized


def _validate_management_state(
    state: dict,
    symbols: list[str],
    sizing_base: float,
    n_tranches: int,
) -> None:
    tranches = state.get("tranches")
    last_target = state.get("last_target")
    if tranches is None and last_target is None:
        return
    if not isinstance(tranches, dict) or not tranches or len(tranches) > n_tranches:
        raise ProprError("stato tranche Propr non valido")
    allowed_slots = {str(slot) for slot in range(n_tranches)}
    if not set(tranches).issubset(allowed_slots):
        raise ProprError("slot tranche Propr non valido")
    aggregate: dict[str, float] = {}
    for tranche in tranches.values():
        validated = _validate_target(
            tranche,
            symbols,
            sizing_base,
            gross_cap=PROPR_GROSS_OVERRIDE / n_tranches,
        )
        for asset, value in validated.items():
            aggregate[asset] = aggregate.get(asset, 0.0) + value
    aggregate = {asset: value for asset, value in aggregate.items() if abs(value) > 1e-9}
    aggregate = _validate_target(aggregate, symbols, sizing_base)
    persisted = _validate_target(last_target, symbols, sizing_base)
    if set(aggregate) != set(persisted) or any(
        abs(aggregate[asset] - persisted[asset]) > 0.10 for asset in aggregate
    ):
        raise ProprError("last_target Propr incoerente con le tranche")


def _validate_paper_attempt(attempt: dict, expected_account_id: str) -> None:
    challenge = attempt.get("challenge") or {}
    if attempt.get("accountId") != expected_account_id:
        raise ProprError("account Propr diverso dal Free Trial autorizzato")
    if attempt.get("status") != "active":
        raise ProprError(f"challenge non attiva (status={attempt.get('status')})")
    if challenge.get("slug") != EXPECTED_CHALLENGE_SLUG:
        raise ProprError("challenge Propr non free-trial")
    if float(challenge.get("initialBalance", 0)) != float(EXPECTED_INITIAL_BALANCE):
        raise ProprError("balance iniziale Propr diverso da $5.000 paper")
    phases = challenge.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ProprError("regole challenge Propr assenti")
    phase = phases[0]
    expected_rules = {
        "profitTargetPercent": float(RULEBOOK["profit_target_pct"]),
        "maxDailyLossPercent": float(RULEBOOK["max_daily_loss_pct"]),
        "maxDrawdownPercent": float(RULEBOOK["max_drawdown_pct"]),
    }
    try:
        observed_rules = {name: float(phase.get(name)) for name in expected_rules}
    except (TypeError, ValueError):
        observed_rules = {}
    if observed_rules != expected_rules:
        raise ProprError(f"regole challenge Propr inattese: {observed_rules}")


def _protection_summary(positions: list[dict], open_orders: list[dict]) -> dict:
    return {
        "mode": "native-stop-market",
        **reconciliation_summary(positions, open_orders),
    }

# decimali quantità per prezzo — approssimazione conservativa, l'API rifiuta
# (e logghiamo) se il tick size è più stretto di quanto assunto qui.
def _qty_decimals(price: float) -> int:
    if price >= 1000:
        return 3
    if price >= 10:
        return 2
    if price >= 1:
        return 1
    return 0


def log_event(ev: dict) -> None:
    ev["ts"] = datetime.now(timezone.utc).isoformat()
    JOURNAL.parent.mkdir(exist_ok=True)
    with open(JOURNAL, "a") as f:
        f.write(json.dumps(ev, default=str) + "\n")


def _signed_notionals(positions: list[dict]) -> dict[str, float]:
    notionals: dict[str, float] = {}
    for position in positions:
        asset = str(position.get("base", ""))
        side = str(position.get("positionSide", "")).lower()
        try:
            notional = float(position.get("notionalValue"))
        except (TypeError, ValueError) as exc:
            raise ProprError(f"notional posizione non valido per {asset}") from exc
        if (
            not asset
            or asset in notionals
            or side not in ("long", "short")
            or not math.isfinite(notional)
            or notional < 0
        ):
            raise ProprError(f"book Propr non valido per {asset or '<vuoto>'}")
        notionals[asset] = notional if side == "long" else -notional
    return notionals


def _exact_position_quantity(position: dict, asset: str) -> str:
    try:
        quantity = abs(Decimal(str(position.get("quantity"))))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProprError(f"quantity posizione non valida per {asset}") from exc
    if not quantity.is_finite() or quantity <= 0:
        raise ProprError(f"quantity posizione non valida per {asset}")
    return format(quantity, "f")


def _signed_quantities(positions: list[dict]) -> dict[str, Decimal]:
    quantities: dict[str, Decimal] = {}
    for position in positions:
        asset = str(position.get("base", ""))
        side = str(position.get("positionSide", "")).lower()
        if not asset or asset in quantities or side not in ("long", "short"):
            raise ProprError(f"book Propr non valido per {asset or '<vuoto>'}")
        quantity = Decimal(_exact_position_quantity(position, asset))
        quantities[asset] = quantity if side == "long" else -quantity
    return quantities


def _require_filled_reduction(response: object, asset: str) -> None:
    if (
        not isinstance(response, list)
        or len(response) != 1
        or not isinstance(response[0], dict)
        or not isinstance(response[0].get("orderId"), str)
        or not response[0]["orderId"].strip()
        or response[0].get("status") != "filled"
    ):
        raise ProprError(f"riduzione non confermata come filled per {asset}")


def _reduction_barrier_errors(
    expected: dict[str, Decimal],
    positions: list[dict],
) -> list[str]:
    observed = _signed_quantities(positions)
    expected_assets = {asset for asset, value in expected.items() if value != 0}
    errors = []
    if set(observed) != expected_assets:
        errors.append(
            "asset("
            f"{','.join(sorted(observed))}!={','.join(sorted(expected_assets))}"
            ")"
        )
    for asset in sorted(expected_assets & set(observed)):
        want = expected[asset]
        have = observed[asset]
        if want * have <= 0 or abs(have - want) > Decimal("1e-8"):
            errors.append(f"{asset}:quantity({have}!={want})")
    return errors


def rebalance(client: ProprClient, target: dict[str, float], px: dict[str, float],
              positions: list[dict]) -> list[dict]:
    """target: {asset: notional con segno}, assenti = flat.

    L'account Propr è NETTED one-way (non hedge-mode nonostante il campo
    positionSide): un solo verificato empiricamente — side/positionSide devono
    SEMPRE accoppiarsi buy+long o sell+short, anche per reduceOnly. Per ridurre
    una posizione si usa il pairing OPPOSTO al segno corrente (es. per chiudere
    uno short si manda buy+long con reduceOnly=true, che netta contro lo short
    esistente). Qui basta calcolare il delta con segno e scegliere side di
    conseguenza — niente bucket long/short separati da gestire."""
    current = _signed_notionals(positions)
    position_by_asset: dict[str, dict] = {}
    position_prices: dict[str, float] = {}
    for p in positions:
        position_by_asset[p["base"]] = p
        if p.get("markPrice") is not None:
            position_prices[p["base"]] = float(p["markPrice"])

    assets = sorted(set(target) | set(current))
    reductions = []
    increases = []
    preflight_errors = []
    for asset in assets:
        want = float(target.get(asset, 0.0))
        have = current.get(asset, 0.0)
        delta = want - have
        closing = have != 0 and want == 0
        flipping = have != 0 and want != 0 and want * have < 0
        if not closing and not flipping and abs(delta) < 5.0:
            continue
        price = px.get(asset, position_prices.get(asset))
        if price is None or not math.isfinite(float(price)) or float(price) <= 0:
            preflight_errors.append(asset)
            continue
        price = float(price)
        dec = _qty_decimals(price)

        if closing or flipping:
            try:
                quantity = _exact_position_quantity(position_by_asset[asset], asset)
            except (KeyError, ProprError):
                preflight_errors.append(asset)
                continue
            close_delta = -have
            reductions.append((
                asset,
                close_delta,
                quantity,
                "buy" if close_delta > 0 else "sell",
                "long" if close_delta > 0 else "short",
                True,
            ))
            if closing:
                continue
            delta = want

        qty = round(abs(delta) / price, dec)
        if qty <= 0:
            continue
        side = "buy" if delta > 0 else "sell"
        position_side = "long" if delta > 0 else "short"
        reduce_only = (
            not flipping
            and have != 0
            and want * have > 0
            and abs(want) < abs(have)
        )
        order = (asset, delta, str(qty), side, position_side, reduce_only)
        (reductions if reduce_only else increases).append(order)
    if preflight_errors:
        raise ProprError("rebalance preflight: prezzo mancante/non valido per "
                         + ", ".join(preflight_errors))
    plan = reductions + increases
    if len(plan) > MAX_ORDERS_PER_ACTION:
        raise ProprError(f"rebalance rifiutato: {len(plan)} ordini > cap {MAX_ORDERS_PER_ACTION}")

    barrier_target = _signed_quantities(positions) if reductions else {}
    for asset, delta, quantity, _side, _position_side, _reduce_only in reductions:
        adjustment = Decimal(quantity) if delta > 0 else -Decimal(quantity)
        remaining = barrier_target[asset] + adjustment
        if remaining != 0 and barrier_target[asset] * remaining <= 0:
            raise ProprError(f"rebalance preflight: riduzione oltre il flat per {asset}")
        barrier_target[asset] = remaining

    results = []
    reduction_failed = False
    for asset, delta, quantity, side, position_side, reduce_only in reductions:
        try:
            r = client.create_order(side=side, position_side=position_side, order_type="market",
                                     asset=asset, quantity=quantity,
                                     reduce_only=reduce_only, close_position=False)
            _require_filled_reduction(r, asset)
            results.append({"asset": asset, "action": "adjust", "side": side,
                             "qty": float(quantity), "delta_usd": round(delta, 2), "resp": r})
            print(f"  {asset}: {side} {quantity} (reduceOnly={reduce_only}) "
                  f"delta {delta:+.0f}$")
        except ProprError as e:
            print(f"  {asset}: ordine fallito: {e}", file=sys.stderr)
            results.append({"asset": asset, "action": "error", "error": str(e)})
            reduction_failed = True

    if reduction_failed:
        return results
    if reductions:
        try:
            barrier_errors = _reduction_barrier_errors(
                barrier_target,
                client.get_positions(),
            )
        except Exception as exc:
            barrier_errors = [f"readback:{type(exc).__name__}:{exc}"]
        if barrier_errors:
            results.append({
                "asset": "barrier",
                "action": "error",
                "error": "riduzioni non confermate: " + ",".join(barrier_errors),
            })
            return results

    for asset, delta, quantity, side, position_side, reduce_only in increases:
        try:
            r = client.create_order(side=side, position_side=position_side, order_type="market",
                                    asset=asset, quantity=quantity,
                                    reduce_only=reduce_only, close_position=False)
            results.append({"asset": asset, "action": "adjust", "side": side,
                            "qty": float(quantity), "delta_usd": round(delta, 2), "resp": r})
            print(f"  {asset}: {side} {quantity} (reduceOnly={reduce_only}) "
                  f"delta {delta:+.0f}$")
        except ProprError as e:
            print(f"  {asset}: ordine fallito: {e}", file=sys.stderr)
            results.append({"asset": asset, "action": "error", "error": str(e)})
            break
    return results


def flatten(client: ProprClient, positions: list[dict]) -> list[dict]:
    """Chiude tutte le posizioni aperte. Pairing OPPOSTO al segno corrente con
    reduceOnly (semantica netted one-way: buy+long chiude short, sell+short
    chiude long); quantity presa dalla posizione, nessun prezzo necessario."""
    plan = sorted(positions, key=lambda p: p["base"])
    if len(plan) > MAX_ORDERS_PER_ACTION:
        raise ProprError(f"flatten rifiutato: {len(plan)} ordini > cap {MAX_ORDERS_PER_ACTION}")
    results = []
    for p in plan:
        is_short = p["positionSide"] == "short"
        side, pos_side = ("buy", "long") if is_short else ("sell", "short")
        qty = str(abs(float(p["quantity"])))
        try:
            r = client.create_order(side=side, position_side=pos_side, order_type="market",
                                     asset=p["base"], quantity=qty,
                                     reduce_only=True, close_position=False)
            results.append({"asset": p["base"], "action": "flatten", "side": side,
                             "qty": qty, "resp": r})
            print(f"  {p['base']}: flatten {side} {qty}")
        except ProprError as e:
            print(f"  {p['base']}: flatten fallito: {e}", file=sys.stderr)
            results.append({"asset": p["base"], "action": "error", "error": str(e)})
    return results


def _raise_on_order_errors(results: list[dict]) -> None:
    failed = [str(r.get("asset")) for r in results if r.get("action") == "error"]
    if failed:
        raise ProprError(f"azione Propr parziale; ordini falliti: {', '.join(failed)}")


def _set_leverage(client: ProprClient, symbols: list[str], want: int) -> None:
    """Alza la leva cross al max consentito (cap dello spec) per ogni asset
    dell'universo — di default Propr apre a leva 1x e con gross=1.0 dollar-neutral
    su N gambe il margine finisce prima di piazzare l'ultima."""
    limits = client.get_leverage_limits()
    for asset in symbols:
        cap = limits.get("overrides", {}).get(asset, limits.get("defaultMax", 2))
        lev = min(want, cap)
        try:
            cfg = client.get_margin_config(asset)
            if int(float(cfg.get("leverage", 1))) >= lev:
                continue
            client.update_margin_config(cfg["configId"], asset, lev)
            print(f"  leverage {asset} -> {lev}x")
        except ProprError as e:
            print(f"  {asset}: leverage config fallita: {e}", file=sys.stderr)


def _paper_track_record(strategy_id: str) -> dict | None:
    """Ultimo evento promote per la strategia dal loop interno (paper/lifecycle.jsonl)
    — il track record che ha reso questa strategia champion prima di girare su Propr."""
    path = ROOT / "paper/lifecycle.jsonl"
    if not path.exists():
        return None
    latest = None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("strategy") == strategy_id and d.get("event") == "promote":
            latest = d
    if not latest:
        return None
    st = latest["stats"]
    return {"n_closed": st["n_closed"], "basket_sharpe_r": st["basket_sharpe_r"],
            "basket_mean_r": st["basket_mean_r"], "win_rate": st["win_rate"],
            "max_drawdown": st["max_drawdown"], "dsr": latest["dsr"],
            "promoted_at": latest["logged_at"]}


def _strategy_detail(spec: dict) -> dict:
    pf = spec["portfolio"]
    bt = (spec.get("backtest") or {}).get("basket_12m", {}).get("aggregate", {})
    return {
        "thesis": spec.get("thesis", "").strip(),
        "universe": spec["paper_symbols"].split(","),
        "lookbacks_h": pf.get("lookbacks_h") or [pf.get("lookback_h")],
        "rebalance_h": pf["rebalance_h"], "long_q": pf.get("long_q"), "short_q": pf.get("short_q"),
        "gross": pf.get("gross", 1.0), "propr_gross_override": PROPR_GROSS_OVERRIDE,
        "propr_daily_stop_pct": PROPR_DAILY_STOP_PCT,
        "propr_tranches": max(1, int(pf["rebalance_h"]) // PROPR_TRANCHE_H),
        "dollar_neutral": pf.get("dollar_neutral", True),
        "max_leverage": spec.get("risk", {}).get("max_leverage"),
        "backtest_12m": {"sharpe": bt.get("sharpe"), "total_return": bt.get("total_return"),
                         "max_drawdown": bt.get("max_drawdown"), "dsr": bt.get("dsr"),
                         "rebalances": bt.get("rebalances")},
        "paper_track_record": _paper_track_record(spec["id"]),
    }


def write_status(client: ProprClient, spec: dict, attempt: dict, positions: list[dict],
                 last_rebalance_ts: str, *, discretionary: bool = False,
                 automanage: bool = False, protection: dict | None = None,
                 evidence: dict | None = None,
                 paper_execution_evidence: dict | None = None) -> None:
    """Snapshot pubblico per la dashboard: stato challenge Propr vs le sue stesse
    regole (target/daily-loss/drawdown), letto dal server — non ricalcolato qui."""
    acct = client.get_account()
    equity = float(acct["balance"]) + float(acct.get("totalUnrealizedPnl", 0.0))
    ch = attempt["challenge"]
    phase = ch["phases"][0]
    start_bal = float(ch["initialBalance"])
    target_pct = float(phase["profitTargetPercent"])
    daily_loss_pct = float(phase["maxDailyLossPercent"])
    dd_pct = float(phase["maxDrawdownPercent"])
    dd_limit = start_bal * (1 - dd_pct / 100)
    hwm = float(acct.get("highWaterMark", start_bal))

    prev = json.loads(STATUS_PATH.read_text()) if STATUS_PATH.exists() else {}
    history = (prev.get("equity_history", []) +
               [{"ts": datetime.now(timezone.utc).isoformat(), "equity": round(equity, 2)}])[-1000:]

    if automanage:
        execution_mode = "systematic-paper-automanage"
        guard_note = ("stop nativi server-side verificati"
                      if protection and protection.get("exactly_one_per_position")
                      else "copertura stop in verifica o incompleta")
        management_note = ("Gestione automatica del solo Free Trial paper: account e rischio "
                           "verificati ogni ora, target aggiornato per tranche ogni 24h, "
                           f"{guard_note}.")
    elif discretionary:
        execution_mode = "llm-discretionary"
        management_note = ("Gestione discrezionale LLM sul solo account paper; "
                           "snapshot API in sola lettura.")
    else:
        execution_mode = "systematic"
        management_note = ""
    paper_execution_blocked = (
        paper_execution_evidence is not None
        and not paper_execution_evidence.get("verified", False)
    )

    status = {
        "strategy": "llm-discretionary-v1" if discretionary else spec["id"],
        "execution_mode": execution_mode,
        "management_note": management_note,
        "automanage_enabled": automanage,
        "paper_only": True,
        "official_candidate": False,
        "realtime_protection": protection or (
            {"mode": "pending-guard", "fully_protected": False}
            if automanage else {"mode": "none", "fully_protected": False}
        ),
        "account_id": attempt["accountId"],
        "challenge": ch["name"], "challenge_slug": ch["slug"],
        "attempt_status": attempt["status"], "started_at": attempt["startedAt"],
        "start_balance": start_bal, "equity": round(equity, 2), "balance": round(float(acct["balance"]), 2),
        "high_water_mark": hwm,
        "profit_target_pct": target_pct, "profit_target_progress_pct": round((equity / start_bal - 1) * 100, 2),
        "max_daily_loss_pct": daily_loss_pct,
        "max_drawdown_pct": dd_pct, "max_drawdown_equity_limit": round(dd_limit, 2),
        "drawdown_room_pct": round((equity - dd_limit) / start_bal * 100, 2),
        "passed": equity >= start_bal * (1 + target_pct / 100),
        "breached": attempt["status"] == "failed",
        "positions": [{"asset": p["base"], "side": p["positionSide"], "notional": round(float(p["notionalValue"]), 2),
                       "unrealized_pnl": round(float(p["unrealizedPnl"]), 2)} for p in positions],
        "last_rebalance_ts": last_rebalance_ts,
        "equity_history": history,
        "strategy_detail": None if discretionary else _strategy_detail(spec),
        "trading_blocked": paper_execution_blocked,
        "trading_block_reason": (
            "paper_execution_evidence_not_verified"
            if paper_execution_blocked else None
        ),
        "evidence": evidence or verify_evidence(spec, ROOT),
        "paper_execution_evidence": paper_execution_evidence,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write_text(STATUS_PATH, json.dumps(status, indent=1))


def main(snapshot_only: bool = False, manage_paper: bool = False) -> None:
    if snapshot_only and manage_paper:
        raise SystemExit("scegliere solo uno tra --snapshot-only e --manage-paper")
    spec = load(SPEC_PATH)
    evidence = verify_evidence(spec, ROOT)
    evidence_was_verified = evidence["verified"]
    if spec.get("status") != "champion":
        evidence["reasons"].append("paper_status_not_champion")
    # Questo executor implementa solo una variante xsmom hard-coded (universo,
    # tranching e gross override): non e ancora una replica verificata di uno
    # spec portfolio generico. Anche con receipt valida resta irraggiungibile.
    if spec.get("engine") == "portfolio":
        evidence["reasons"].append("portfolio_execution_contract_not_verified")
    if evidence["reasons"]:
        evidence.update(verified=False, status="blocked")
    if snapshot_only:
        automanage_requested = _enabled("PROPR_AUTOMANAGE_ENABLED")
        guard_requested = _enabled("PROPR_GUARD_ENABLED")
        protected_mode_requested = automanage_requested or guard_requested
        expected_account_id = os.environ.get("PROPR_EXPECTED_ACCOUNT_ID", "").strip()
        if protected_mode_requested and not expected_account_id:
            raise SystemExit("PROPR_EXPECTED_ACCOUNT_ID obbligatorio con guard o automanage")
        paper_execution_evidence = (
            verify_propr_paper_evidence(
                spec,
                ROOT,
                account_id=expected_account_id,
                execution_contract=_paper_execution_contract(spec),
            )
            if protected_mode_requested
            else None
        )
        client = ProprClient(read_only=True)
        client.setup(expected_account_id=expected_account_id or None,
                     expected_challenge_slug="free-trial" if protected_mode_requested else None)
        attempt = client.active_attempt
        if protected_mode_requested:
            _validate_paper_attempt(attempt, expected_account_id)
        positions = client.get_positions()
        state = _read_state()
        automanage = (automanage_requested and
                      state.get("management_mode") == AUTOMANAGE_VERSION)
        protection = (_protection_summary(positions, client.get_active_orders())
                      if guard_requested else None)
        write_status(client, spec, attempt, positions, state.get("last_rebalance_ts", ""),
                     discretionary=not automanage, automanage=automanage,
                     protection=protection, evidence=evidence,
                     paper_execution_evidence=paper_execution_evidence)
        print("propr snapshot read-only aggiornato; nessun ordine automatico")
        return
    if manage_paper and not _enabled("PROPR_AUTOMANAGE_ENABLED"):
        print("propr automanage disabilitato dal kill switch")
        return
    if manage_paper and not _enabled("PROPR_GUARD_ENABLED"):
        print("propr automanage bloccato: guard native disabilitato")
        return
    if manage_paper and not os.environ.get("PROPR_EXPECTED_ACCOUNT_ID", "").strip():
        raise SystemExit("PROPR_EXPECTED_ACCOUNT_ID obbligatorio con --manage-paper")
    paper_execution_evidence = None
    blocked_reason = None
    blocked_evidence = evidence
    blocked_evidence_key = "evidence"
    if manage_paper:
        paper_execution_evidence = verify_propr_paper_evidence(
            spec,
            ROOT,
            account_id=os.environ["PROPR_EXPECTED_ACCOUNT_ID"].strip(),
            execution_contract=_paper_execution_contract(spec),
        )
        if not paper_execution_evidence["verified"]:
            blocked_reason = "paper_execution_evidence_not_verified"
            blocked_evidence = paper_execution_evidence
            blocked_evidence_key = "paper_execution_evidence"
    elif not evidence["verified"]:
        blocked_reason = ("portfolio_execution_contract_not_verified"
                          if evidence_was_verified and spec.get("engine") == "portfolio"
                          else "evidence_not_verified")
    if blocked_reason:
        # Gate before ProprClient: no account, market-data or order endpoint is
        # reachable while the maker/checker evidence pair is absent or invalid.
        try:
            previous = json.loads(STATUS_PATH.read_text()) if STATUS_PATH.exists() else {}
        except (OSError, json.JSONDecodeError):
            previous = {}
        previous.update({
            "strategy": spec.get("id"),
            "trading_blocked": True,
            "trading_block_reason": blocked_reason,
            blocked_evidence_key: blocked_evidence,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        atomic_write_text(STATUS_PATH, json.dumps(previous, indent=1))
        print(f"propr bloccato: evidenza non verificata "
              f"({', '.join(blocked_evidence['reasons'])})",
              file=sys.stderr)
        raise SystemExit(2)
    pf = spec["portfolio"]
    symbols = [s for s in spec["paper_symbols"].split(",") if s]
    multi_horizon = pf.get("lookbacks_h")
    lookback_h = int(multi_horizon[0]) if multi_horizon else int(pf["lookback_h"])
    rebalance_h = int(pf["rebalance_h"])
    gross = PROPR_GROSS_OVERRIDE

    client = ProprClient()
    expected_account_id = os.environ.get("PROPR_EXPECTED_ACCOUNT_ID", "").strip()
    account_id = client.setup(expected_account_id=expected_account_id if manage_paper else None,
                              expected_challenge_slug="free-trial" if manage_paper else None)
    attempt = client.active_attempt
    if manage_paper:
        _validate_paper_attempt(attempt, expected_account_id)
        protection = _protection_summary(
            client.get_positions(),
            client.get_active_orders(),
        )
        if not protection["exactly_one_per_position"]:
            raise ProprError(
                "automanage bloccato: riconciliazione stop non esatta "
                f"(positions={protection['open_positions']}, "
                f"orders={protection['active_protective_orders']}, "
                f"duplicates={protection['duplicate_protective_orders']}, "
                f"unmatched={protection['unmatched_protective_orders']}, "
                f"unexpected={protection['unexpected_active_orders']})"
            )
    if attempt["status"] != "active":
        print(f"challenge non attiva (status={attempt['status']}), skip trading")
        return
    acct = client.get_account()
    equity = float(acct["balance"]) + float(acct.get("totalUnrealizedPnl", 0.0))
    # sizing fisso su balance iniziale della challenge (non su equity compounded) —
    # parte del risk overlay, evita che il gross effettivo cresca coi profitti
    sizing_base = float(attempt["challenge"]["initialBalance"])
    print(f"propr paper {spec['id']} account={account_id} equity={equity:.2f}$ "
          f"sizing_base={sizing_base:.2f}$ gross_override={gross}")

    local_state = _read_state()
    if manage_paper and local_state.get("management_mode") != AUTOMANAGE_VERSION:
        local_state = _fresh_management_state(equity, datetime.now(timezone.utc))
        print("  stato automanage inizializzato; target e tranche legacy ignorati")
    last_rb = local_state.get("last_rebalance_ts", "")
    from datetime import timedelta
    # con tranching il runner gira ogni PROPR_TRANCHE_H (sostituisce 1 tranche);
    # la cadenza effettiva per sub-book resta rebalance_h dello spec
    n_tranches = max(1, int(rebalance_h) // PROPR_TRANCHE_H)
    if manage_paper:
        _validate_management_state(local_state, symbols, sizing_base, n_tranches)
    due = (not last_rb or
           datetime.now(timezone.utc) - datetime.fromisoformat(last_rb) >= timedelta(hours=PROPR_TRANCHE_H))

    # --- circuit breaker giornaliero (vedi PROPR_DAILY_STOP_PCT) ---
    today = datetime.now(timezone.utc).date().isoformat()
    daily_stop = sizing_base * PROPR_DAILY_STOP_PCT
    reenter = False
    if local_state.get("day_date") != today:
        # nuovo giorno UTC: snapshot equity; se ieri eravamo flat da breaker,
        # re-entry sull'ultimo target salvato (preserva la cadenza segnale 168h)
        reenter = bool(local_state.get("halted_today")) and bool(local_state.get("last_target"))
        local_state.update({"day_date": today, "day_start_equity": equity, "halted_today": False})
    halted = bool(local_state.get("halted_today"))
    day_start_eq = float(local_state.get("day_start_equity", equity))

    positions = client.get_positions()
    if not halted and equity - day_start_eq <= -daily_stop:
        print(f"  CIRCUIT BREAKER: P&L giornata {equity - day_start_eq:+.0f}$ <= -{daily_stop:.0f}$, flat fino a mezzanotte UTC")
        results = flatten(client, positions)
        log_event({"type": "circuit_breaker", "strategy": spec["id"], "account_id": account_id,
                   "equity": round(equity, 2), "day_start_equity": round(day_start_eq, 2),
                   "day_pnl": round(equity - day_start_eq, 2), "orders": results})
        if manage_paper:
            _raise_on_order_errors(results)
        local_state["halted_today"] = True
        halted = True
        positions = client.get_positions()

    if halted:
        print("  halted da circuit breaker, no trading fino a mezzanotte UTC")
    elif due or reenter:
        rets, px = trailing_returns(symbols, lookback_h, multi_horizon)
        if not px:
            print("nessun prezzo disponibile, skip rebalance")
        elif reenter and not due:
            # re-entry post-breaker: ripristina il target dell'ultimo rebalance
            target = _validate_target(
                local_state["last_target"], symbols, sizing_base)
            print(f"  RE-ENTRY post-breaker: ripristino {len(target)} gambe")
            _set_leverage(client, symbols, int(spec.get("risk", {}).get("max_leverage", 2)))
            results = rebalance(client, target, px, positions)
            log_event({"type": "reentry", "strategy": spec["id"], "account_id": account_id,
                       "equity": round(equity, 2), "target": {k: round(v, 2) for k, v in target.items()},
                       "orders": results})
            if manage_paper:
                _raise_on_order_errors(results)
            positions = client.get_positions()
        else:
            w = xs_momentum_weights(rets, long_q=float(pf.get("long_q", 0.66)),
                                     short_q=float(pf.get("short_q", 0.33)), gross=gross,
                                     dollar_neutral=bool(pf.get("dollar_neutral", True)))
            tranche = {s: float(w[s]) * sizing_base / n_tranches
                       for s in w.index if abs(w[s]) > 1e-9}
            tranches = local_state.get("tranches") or {}
            if not tranches:
                # bootstrap: seed di tutte le tranche col segnale corrente — book
                # subito pieno, la diversificazione di fase si costruisce in 7gg
                tranches = {str(k): dict(tranche) for k in range(n_tranches)}
                slot = "seed"
            else:
                slot = str(datetime.now(timezone.utc).toordinal() % n_tranches)
                tranches[slot] = tranche
            target: dict[str, float] = {}
            for t in tranches.values():
                for a, v in t.items():
                    target[a] = target.get(a, 0.0) + float(v)
            target = {a: v for a, v in target.items() if abs(v) > 1e-9}
            target = _validate_target(target, symbols, sizing_base)
            print(f"  TRANCHE {slot}/{n_tranches}: target book {len(target)} gambe su {len(px)} prezzi")
            _set_leverage(client, symbols, int(spec.get("risk", {}).get("max_leverage", 2)))
            results = rebalance(client, target, px, positions)
            log_event({"type": "rebalance", "strategy": spec["id"], "account_id": account_id,
                       "equity": round(equity, 2), "tranche_slot": slot,
                       "target": {k: round(v, 2) for k, v in target.items()},
                       "orders": results})
            if manage_paper:
                _raise_on_order_errors(results)
            last_rb = datetime.now(timezone.utc).isoformat()
            local_state["last_rebalance_ts"] = last_rb
            local_state["tranches"] = {k: {a: round(v, 2) for a, v in t.items()}
                                        for k, t in tranches.items()}
            local_state["last_target"] = {k: round(v, 2) for k, v in target.items()}
            positions = client.get_positions()
    else:
        print(f"  no rebalance (prossima tranche tra <= {PROPR_TRANCHE_H}h da {last_rb})")
    local_state["last_manage_check_ts"] = datetime.now(timezone.utc).isoformat()
    atomic_write_text(STATE_PATH, json.dumps(local_state, indent=1))

    write_status(client, spec, attempt, positions, last_rb, automanage=manage_paper,
                 evidence=evidence, paper_execution_evidence=paper_execution_evidence)
    acct_after = client.get_account()
    print(f"fine: balance {acct_after['balance']}$, hwm {acct_after.get('highWaterMark')}$")


if __name__ == "__main__":
    main(snapshot_only="--snapshot-only" in sys.argv[1:],
         manage_paper="--manage-paper" in sys.argv[1:])
