"""Esegue la strategia champion (xsmom-multihorizon-v1) sull'account paper Propr.

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
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.portfolio import xs_momentum_weights
from backtest.strategy import load
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
    for p in positions:
        sign = 1.0 if p["positionSide"] == "long" else -1.0
        current[p["base"]] = current.get(p["base"], 0.0) + sign * float(p["notionalValue"])

    assets = set(target) | set(current)
    results = []
    for asset in assets:
        want = target.get(asset, 0.0)
        have = current.get(asset, 0.0)
        delta = want - have
        if abs(delta) < 5.0:
            continue
        price = px.get(asset)
        if not price:
            print(f"  {asset}: no prezzo, skip", file=sys.stderr)
            continue
        dec = _qty_decimals(price)
        qty = round(abs(delta) / price, dec)
        if qty <= 0:
            continue

        side = "buy" if delta > 0 else "sell"
        position_side = "long" if delta > 0 else "short"
        # reduceOnly solo se stiamo restringendo verso zero senza cambiare segno
        # (stesso segno di have e |want| < |have|, oppure target flat)
        reduce_only = have != 0 and (want == 0 or (want * have > 0 and abs(want) < abs(have)))
        try:
            r = client.create_order(side=side, position_side=position_side, order_type="market",
                                     asset=asset, quantity=str(qty),
                                     reduce_only=reduce_only, close_position=False)
            results.append({"asset": asset, "action": "adjust", "side": side,
                             "qty": qty, "delta_usd": round(delta, 2), "resp": r})
            print(f"  {asset}: {side} {qty} (reduceOnly={reduce_only}) delta {delta:+.0f}$")
        except ProprError as e:
            print(f"  {asset}: ordine fallito: {e}", file=sys.stderr)
    return results


def flatten(client: ProprClient, positions: list[dict]) -> list[dict]:
    """Chiude tutte le posizioni aperte. Pairing OPPOSTO al segno corrente con
    reduceOnly (semantica netted one-way: buy+long chiude short, sell+short
    chiude long); quantity presa dalla posizione, nessun prezzo necessario."""
    results = []
    for p in positions:
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
    return results


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
        "dollar_neutral": pf.get("dollar_neutral", True),
        "max_leverage": spec.get("risk", {}).get("max_leverage"),
        "backtest_12m": {"sharpe": bt.get("sharpe"), "total_return": bt.get("total_return"),
                         "max_drawdown": bt.get("max_drawdown"), "dsr": bt.get("dsr"),
                         "rebalances": bt.get("rebalances")},
        "paper_track_record": _paper_track_record(spec["id"]),
    }


def write_status(client: ProprClient, spec: dict, attempt: dict, positions: list[dict],
                 last_rebalance_ts: str) -> None:
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

    status = {
        "strategy": spec["id"], "account_id": attempt["accountId"],
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
        "strategy_detail": _strategy_detail(spec),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    STATUS_PATH.write_text(json.dumps(status, indent=1))


def main() -> None:
    spec = load(SPEC_PATH)
    pf = spec["portfolio"]
    symbols = [s for s in spec["paper_symbols"].split(",") if s]
    multi_horizon = pf.get("lookbacks_h")
    lookback_h = int(multi_horizon[0]) if multi_horizon else int(pf["lookback_h"])
    rebalance_h = int(pf["rebalance_h"])
    gross = PROPR_GROSS_OVERRIDE

    client = ProprClient()
    account_id = client.setup()
    attempt = client._req("GET", "/challenge-attempts", params={"status": "active"})["data"][0]
    if attempt["status"] != "active":
        print(f"challenge non attiva (status={attempt['status']}), skip trading")
        return
    _set_leverage(client, symbols, int(spec.get("risk", {}).get("max_leverage", 2)))
    acct = client.get_account()
    equity = float(acct["balance"]) + float(acct.get("totalUnrealizedPnl", 0.0))
    # sizing fisso su balance iniziale della challenge (non su equity compounded) —
    # parte del risk overlay, evita che il gross effettivo cresca coi profitti
    sizing_base = float(attempt["challenge"]["initialBalance"])
    print(f"propr paper {spec['id']} account={account_id} equity={equity:.2f}$ "
          f"sizing_base={sizing_base:.2f}$ gross_override={gross}")

    local_state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    last_rb = local_state.get("last_rebalance_ts", "")
    from datetime import timedelta
    due = (not last_rb or
           datetime.now(timezone.utc) - datetime.fromisoformat(last_rb) >= timedelta(hours=rebalance_h))

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
            target = {k: float(v) for k, v in local_state["last_target"].items()}
            print(f"  RE-ENTRY post-breaker: ripristino {len(target)} gambe")
            results = rebalance(client, target, px, positions)
            log_event({"type": "reentry", "strategy": spec["id"], "account_id": account_id,
                       "equity": round(equity, 2), "target": {k: round(v, 2) for k, v in target.items()},
                       "orders": results})
            positions = client.get_positions()
        else:
            w = xs_momentum_weights(rets, long_q=float(pf.get("long_q", 0.66)),
                                     short_q=float(pf.get("short_q", 0.33)), gross=gross,
                                     dollar_neutral=bool(pf.get("dollar_neutral", True)))
            target = {s: float(w[s]) * sizing_base for s in w.index if abs(w[s]) > 1e-9}
            print(f"  REBALANCE dovuto: target {len(target)} gambe su {len(px)} prezzi")
            results = rebalance(client, target, px, positions)
            log_event({"type": "rebalance", "strategy": spec["id"], "account_id": account_id,
                       "equity": round(equity, 2), "target": {k: round(v, 2) for k, v in target.items()},
                       "orders": results})
            last_rb = datetime.now(timezone.utc).isoformat()
            local_state["last_rebalance_ts"] = last_rb
            local_state["last_target"] = {k: round(v, 2) for k, v in target.items()}
            positions = client.get_positions()
    else:
        print(f"  no rebalance (prossimo tra <= {rebalance_h}h da {last_rb})")
    STATE_PATH.write_text(json.dumps(local_state, indent=1))

    write_status(client, spec, attempt, positions, last_rb)
    acct_after = client.get_account()
    print(f"fine: balance {acct_after['balance']}$, hwm {acct_after.get('highWaterMark')}$")


if __name__ == "__main__":
    main()
