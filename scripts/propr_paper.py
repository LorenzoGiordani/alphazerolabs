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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.evidence import verify_evidence
from backtest.portfolio import xs_momentum_weights
from backtest.strategy import load
from pipeline.live import atomic_write_text
from scripts.portfolio_paper import trailing_returns
from scripts.propr_client import ProprClient, ProprError

SPEC_PATH = ROOT / "strategies/generated/xsmom-multihorizon-v1.yaml"
JOURNAL = ROOT / "paper/propr_journal.jsonl"
STATUS_PATH = ROOT / "paper/propr_status.json"
STATE_PATH = ROOT / "paper/propr_state.json"

# Risk overlay Propr-aware, non nello spec (quello resta la champion "pura" per
# backtest/paper interno). Simulazione esatta challenge (daily loss 3% $150,
# drawdown statico 6% $4.7k, path orario 12 mesi): a gross 1.0 sizing su equity
# compounded la challenge si passa al giorno 63 ma l'account muore 3gg dopo per
# breach daily-loss. Solo gross ~0.3 con sizing fisso su balance iniziale (non
# compounded) sopravvive tutto l'anno senza breach. Vedi daily note 2026-07-09.
PROPR_GROSS_OVERRIDE = 0.3
# Circuit breaker giornaliero: se il P&L di giornata (da snapshot equity al primo
# run del giorno UTC) scende sotto -2% del balance iniziale ($100 su $5k), flat
# totale fino a mezzanotte UTC, poi re-entry sull'ultimo target salvato. Monte
# Carlo (1000 path bootstrap 168h): breach 12m 6.4% -> 2.6%, pass 94.3% -> 95.4%,
# stesso tempo mediano. Latenza 1h del cron orario già modellata nella sim.
# Il vol targeting è stato testato e FALSIFICATO (peggiora: vol clustering).
PROPR_DAILY_STOP_PCT = 0.02
# Tranching (portafogli sovrapposti alla Jegadeesh-Titman): il backtest reb168
# è fragile alla FASE del rebalance (Sharpe 1.10-2.86, media 2.15, a seconda
# dell'ora in cui cade il ribilancio settimanale). Fix: 7 sub-book da 1/7 del
# capitale, ognuno ribilanciato settimanalmente ma in un giorno diverso (slot =
# ordinale del giorno UTC % 7). Elimina la lotteria di fase e alza lo Sharpe
# fase-mediato a 2.51 (test 2.57). Costi modellati per sub-book: il netting
# reale degli ordini a livello asset può solo ridurli. Vedi daily 2026-07-09.
PROPR_TRANCHE_H = 24
AUTOMANAGE_VERSION = "systematic-paper-automanage-v1"
MAX_ORDERS_PER_ACTION = 12


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


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


def _validate_paper_attempt(attempt: dict, expected_account_id: str) -> None:
    challenge = attempt.get("challenge") or {}
    if attempt.get("accountId") != expected_account_id:
        raise ProprError("account Propr diverso dal Free Trial autorizzato")
    if attempt.get("status") != "active":
        raise ProprError(f"challenge non attiva (status={attempt.get('status')})")
    if challenge.get("slug") != "free-trial":
        raise ProprError("challenge Propr non free-trial")
    if float(challenge.get("initialBalance", 0)) != 5000.0:
        raise ProprError("balance iniziale Propr diverso da $5.000 paper")


def _protection_summary(positions: list[dict], open_orders: list[dict]) -> dict:
    position_by_id = {str(p["positionId"]): p for p in positions if p.get("positionId")}
    position_ids = set(position_by_id)
    protected_ids = set()
    for order in open_orders:
        position_id = str(order.get("positionId", ""))
        position = position_by_id.get(position_id)
        if not position:
            continue
        position_side = str(position.get("positionSide", "")).lower()
        closing_side = "sell" if position_side == "long" else "buy" if position_side == "short" else ""
        order_position_side = "long" if closing_side == "buy" else "short" if closing_side else ""
        if (order.get("type") == "stop_market" and closing_side
                and str(order.get("side", "")).lower() == closing_side
                and str(order.get("positionSide", "")).lower() == order_position_side
                and order.get("reduceOnly") is True and order.get("closePosition") is True):
            protected_ids.add(position_id)
    covered = position_ids & protected_ids
    return {
        "mode": "native-stop-market",
        "open_positions": len(position_ids),
        "protected_positions": len(covered),
        "fully_protected": covered == position_ids,
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
    current: dict[str, float] = {}
    position_prices: dict[str, float] = {}
    for p in positions:
        sign = 1.0 if p["positionSide"] == "long" else -1.0
        current[p["base"]] = current.get(p["base"], 0.0) + sign * float(p["notionalValue"])
        if p.get("markPrice") is not None:
            position_prices[p["base"]] = float(p["markPrice"])

    assets = sorted(set(target) | set(current))
    plan = []
    preflight_errors = []
    for asset in assets:
        want = target.get(asset, 0.0)
        have = current.get(asset, 0.0)
        delta = want - have
        if abs(delta) < 5.0:
            continue
        price = px.get(asset, position_prices.get(asset))
        if price is None or not math.isfinite(float(price)) or float(price) <= 0:
            preflight_errors.append(asset)
            continue
        price = float(price)
        dec = _qty_decimals(price)
        qty = round(abs(delta) / price, dec)
        if qty <= 0:
            continue
        side = "buy" if delta > 0 else "sell"
        position_side = "long" if delta > 0 else "short"
        reduce_only = have != 0 and (want == 0 or (want * have > 0 and abs(want) < abs(have)))
        plan.append((asset, delta, qty, side, position_side, reduce_only))
    if preflight_errors:
        raise ProprError("rebalance preflight: prezzo mancante/non valido per "
                         + ", ".join(preflight_errors))
    if len(plan) > MAX_ORDERS_PER_ACTION:
        raise ProprError(f"rebalance rifiutato: {len(plan)} ordini > cap {MAX_ORDERS_PER_ACTION}")

    results = []
    for asset, delta, qty, side, position_side, reduce_only in plan:
        try:
            r = client.create_order(side=side, position_side=position_side, order_type="market",
                                     asset=asset, quantity=str(qty),
                                     reduce_only=reduce_only, close_position=False)
            results.append({"asset": asset, "action": "adjust", "side": side,
                             "qty": qty, "delta_usd": round(delta, 2), "resp": r})
            print(f"  {asset}: {side} {qty} (reduceOnly={reduce_only}) delta {delta:+.0f}$")
        except ProprError as e:
            print(f"  {asset}: ordine fallito: {e}", file=sys.stderr)
            results.append({"asset": asset, "action": "error", "error": str(e)})
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
                 evidence: dict | None = None) -> None:
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
                      if protection and protection.get("fully_protected")
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

    status = {
        "strategy": "llm-discretionary-v1" if discretionary else spec["id"],
        "execution_mode": execution_mode,
        "management_note": management_note,
        "automanage_enabled": automanage,
        "paper_only": True,
        "official_candidate": False,
        "realtime_protection": (protection or {"mode": "pending-guard", "fully_protected": False}
                                if automanage else {"mode": "none", "fully_protected": False}),
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
        "trading_blocked": False,
        "evidence": evidence or verify_evidence(spec, ROOT),
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
        expected_account_id = os.environ.get("PROPR_EXPECTED_ACCOUNT_ID", "").strip()
        if automanage_requested and not expected_account_id:
            raise SystemExit("PROPR_EXPECTED_ACCOUNT_ID obbligatorio con automanage")
        client = ProprClient(read_only=True)
        client.setup(expected_account_id=expected_account_id or None,
                     expected_challenge_slug="free-trial" if automanage_requested else None)
        attempt = client.active_attempt
        if automanage_requested:
            _validate_paper_attempt(attempt, expected_account_id)
        positions = client.get_positions()
        state = _read_state()
        automanage = (automanage_requested and
                      state.get("management_mode") == AUTOMANAGE_VERSION)
        protection = (_protection_summary(positions, client.get_orders(status="open"))
                      if automanage else None)
        write_status(client, spec, attempt, positions, state.get("last_rebalance_ts", ""),
                     discretionary=not automanage, automanage=automanage,
                     protection=protection, evidence=evidence)
        print("propr snapshot read-only aggiornato; nessun ordine automatico")
        return
    if manage_paper and not _enabled("PROPR_AUTOMANAGE_ENABLED"):
        print("propr automanage disabilitato dal kill switch")
        return
    if manage_paper and not os.environ.get("PROPR_EXPECTED_ACCOUNT_ID", "").strip():
        raise SystemExit("PROPR_EXPECTED_ACCOUNT_ID obbligatorio con --manage-paper")
    if not manage_paper and not evidence["verified"]:
        # Gate before ProprClient: no account, market-data or order endpoint is
        # reachable while the maker/checker evidence pair is absent or invalid.
        try:
            previous = json.loads(STATUS_PATH.read_text()) if STATUS_PATH.exists() else {}
        except (OSError, json.JSONDecodeError):
            previous = {}
        previous.update({
            "strategy": spec.get("id"),
            "trading_blocked": True,
            "trading_block_reason": ("portfolio_execution_contract_not_verified"
                                      if evidence_was_verified and spec.get("engine") == "portfolio"
                                      else "evidence_not_verified"),
            "evidence": evidence,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        atomic_write_text(STATUS_PATH, json.dumps(previous, indent=1))
        print(f"propr bloccato: evidenza non verificata ({', '.join(evidence['reasons'])})",
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
        _set_leverage(client, symbols, int(spec.get("risk", {}).get("max_leverage", 2)))
        rets, px = trailing_returns(symbols, lookback_h, multi_horizon)
        if not px:
            print("nessun prezzo disponibile, skip rebalance")
        elif reenter and not due:
            # re-entry post-breaker: ripristina il target dell'ultimo rebalance
            target = {k: float(v) for k, v in local_state["last_target"].items()}
            print(f"  RE-ENTRY post-breaker: ripristino {len(target)} gambe")
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
            print(f"  TRANCHE {slot}/{n_tranches}: target book {len(target)} gambe su {len(px)} prezzi")
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
                 evidence=evidence)
    acct_after = client.get_account()
    print(f"fine: balance {acct_after['balance']}$, hwm {acct_after.get('highWaterMark')}$")


if __name__ == "__main__":
    main(snapshot_only="--snapshot-only" in sys.argv[1:],
         manage_paper="--manage-paper" in sys.argv[1:])
