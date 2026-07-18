"""Executor paper per strategie a PORTAFOGLIO (engine: portfolio).

Tiene un book cross-asset con pesi continui (es. cross-sectional momentum
dollar-neutral) e ribilancia ogni `rebalance_h`. Diverso dal loop per-simbolo
(paper_trade.py): niente stop intrabar per posizione — il rischio è gross
leverage + dollar-neutrality + ribilanciamento. Mark-to-market a ogni run.

Stato in paper/state.json sotto l'id della strategia; eventi in journal.
Stesse fee/slippage dell'engine. Account fittizio 10k$, prezzi reali HL.

Uso: uv run scripts/portfolio_paper.py strategies/generated/xsmom-port-v1.yaml
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.engine import DEFAULT_SLIPPAGE, HL_TAKER_FEE
from backtest.portfolio import sign_weights, xs_momentum_weights
from backtest.lifecycle import paper_symbols
from backtest.strategy import load
from pipeline.live import atomic_write_text, fetch_candles_cached, perp_market_snapshot
from scripts.paper_trade import STATE_FILE, log_event
from scripts.runtime_health import write_coverage

# Cache-backed candle-only seam kept as ``fetch_live`` for deterministic unit
# tests. I factor portfolio non usano funding: evitarlo dimezza richieste/peso API.
fetch_live = fetch_candles_cached

COST = HL_TAKER_FEE + DEFAULT_SLIPPAGE

# Vol-target overlay (Moreira-Muir 2017): scala il gross inverso alla vol realizzata
# del book. Cablato qui per i candidati con portfolio.vol_target.enabled=true.
# Cron ogni 4h -> annualizzo per sqrt(PERIODS_PER_YEAR_HEARTBEAT). Warmup m=1.0.
PERIODS_PER_YEAR_HEARTBEAT = 6 * 365   # heartbeat ogni 4h


def _vol_target_multiplier(history: list, vt: dict) -> float:
    """m = clip(target_vol / realized_vol, gross_floor, gross_cap).
    history: lista di dict {"ts", "eq"} passati (anti-lookahead: solo <= now).
    Ritorna 1.0 in warmup (< min_periods punti)."""
    if not vt or not vt.get("enabled"):
        return 1.0
    min_p = int(vt.get("vol_window_h", 720)) // 4          # ~punti heartbeat necessari
    min_p = max(min_p, 30)
    eqs = [float(h["eq"]) for h in history if h.get("eq")]
    if len(eqs) < min_p:
        return 1.0                                       # warmup
    import numpy as _np
    window = eqs[-min_p:]
    rets = _np.diff(window) / _np.array(window[:-1])
    if len(rets) < 5 or _np.std(rets) <= 0:
        return 1.0
    realized_ann = float(_np.std(rets) * _np.sqrt(PERIODS_PER_YEAR_HEARTBEAT))
    target = float(vt.get("target_vol_ann", 0.20))
    m = target / realized_ann
    return float(_np.clip(m, float(vt.get("gross_floor", 0.3)), float(vt.get("gross_cap", 1.5))))


def trailing_returns(symbols: list[str], lookback_h: int,
                    multi_horizon: list[int] | None = None) -> tuple[pd.Series, dict]:
    """Ritorno trailing per simbolo + ultimo prezzo. Salta i simboli senza dati.
    multi_horizon: se passato ([96,168,336]), ritorna la MEDIA normalizzata dei rank
    su piu' orizzonti (xsmom-multihorizon)."""
    if multi_horizon:
        # media dei rank cross-section normalizzati su ogni orizzonte
        rank_acc, px = {}, {}
        for s in symbols:
            try:
                c = fetch_live(s, lookback_h=max(multi_horizon) + 5)["candles"]
            except Exception as e:
                print(f"  {s}: fetch fallito ({e})", file=sys.stderr)
                continue
            if c.empty:
                continue
            last = float(c.close.iloc[-1])
            if not math.isfinite(last) or last <= 0:
                continue
            px[s] = last
            if len(c) <= max(multi_horizon):
                continue
            rank_acc[s] = []
            for lb in multi_horizon:
                rank_acc[s].append(float(c.close.iloc[-1] / c.close.iloc[-1 - lb] - 1.0))
        # media dei ritorni trailing normalizzati per asset (proxy multi-orizzonte onesto)
        rets = {s: float(np.mean(rs)) for s, rs in rank_acc.items()
                if rs and math.isfinite(float(np.mean(rs)))}
        return pd.Series(rets), px
    rets, px = {}, {}
    for s in symbols:
        try:
            c = fetch_live(s, lookback_h=lookback_h + 5)["candles"]
        except Exception as e:
            print(f"  {s}: fetch fallito ({e})", file=sys.stderr)
            continue
        if c.empty:
            continue
        last = float(c.close.iloc[-1])
        if not math.isfinite(last) or last <= 0:
            continue
        px[s] = last
        if len(c) <= lookback_h:
            continue
        base = float(c.close.iloc[-1 - lookback_h])
        if base > 0:
            value = last / base - 1.0
            if math.isfinite(value):
                rets[s] = value
    return pd.Series(rets), px


def vol_signal(symbols: list[str], lookback_h: int) -> tuple[pd.Series, dict]:
    """HIGH-VOL factor: per ogni asset la dev-standard dei rendimenti orari trailing.
    xs_momentum_weights poi long-top (i piu' volatili) / short-bottom (calmi).
    Risk premium crypto, ortogonale al momentum (ranka vol, non ret)."""
    vols, px = {}, {}
    for s in symbols:
        try:
            c = fetch_live(s, lookback_h=lookback_h + 5)["candles"]
        except Exception as e:
            print(f"  {s}: fetch fallito ({e})", file=sys.stderr)
            continue
        if c.empty:
            continue
        last = float(c.close.iloc[-1])
        if not math.isfinite(last) or last <= 0:
            continue
        px[s] = last
        if len(c) <= lookback_h:
            continue
        r = c.close.pct_change().iloc[-lookback_h:]
        value = float(r.std())
        if math.isfinite(value):
            vols[s] = value
    return pd.Series(vols), px


def liqimb_signal(symbols: list[str], lookback_d: int) -> tuple[pd.Series, dict]:
    """LIQIMB factor: sbilancio liquidazioni (liq_short - liq_long)/oi, media
    rolling su lookback_d giorni. Long dove gli short vengono squeezati (FOLLOW,
    lezione 14/06: il fade perde). Fonte: data/coinalyze_1h/ (refresh cron cloud
    6h) — solo barre passate, anti-lookahead by-construction. Prezzi live HL."""
    sigs, px = {}, {}
    min_bars = lookback_d * 12                     # tolleranza buchi del collector
    required_columns = {"ts", "liq_short", "liq_long", "oi"}
    for s in symbols:
        try:
            candles = fetch_live(s, lookback_h=8)["candles"]
            last = float(candles.close.iloc[-1])
            if not math.isfinite(last) or last <= 0:
                raise ValueError("prezzo non valido")
            px[s] = last
        except Exception as e:
            print(f"  {s}: prezzo live fallito ({e})", file=sys.stderr)
            continue
        p = ROOT / f"data/coinalyze_1h/{s}.parquet"
        if not p.exists():
            print(f"  {s}: sorgente Coinalyze assente", file=sys.stderr)
            continue
        try:
            c = pd.read_parquet(p).drop_duplicates("ts").sort_values("ts")
        except Exception as e:
            print(f"  {s}: coinalyze_1h illeggibile ({e})", file=sys.stderr)
            continue
        if not required_columns.issubset(c.columns):
            print(f"  {s}: colonne Coinalyze incomplete", file=sys.stderr)
            continue
        tail = c.tail(lookback_d * 24)
        if len(tail) < min_bars:
            print(f"  {s}: storico Coinalyze insufficiente", file=sys.stderr)
            continue
        last_source_ts = pd.to_datetime(tail.ts.iloc[-1], utc=True, errors="coerce")
        age_h = (pd.Timestamp.now(tz="UTC") - last_source_ts).total_seconds() / 3600
        if pd.isna(last_source_ts) or age_h < -1 or age_h > 8:
            print(f"  {s}: sorgente Coinalyze stale ({age_h:.1f}h)", file=sys.stderr)
            continue
        imb = ((tail.liq_short - tail.liq_long) / tail.oi.replace(0, np.nan)).mean()
        if pd.isna(imb):
            continue
        value = float(imb)
        if math.isfinite(value):
            sigs[s] = value
    return pd.Series(sigs), px


def combo_signal(symbols: list[str], factors: list[str], weights: list[float],
                 lookback_h: int, vol_lookback_h: int) -> tuple[pd.Series, dict]:
    """COMBO multi-fattore: media pesata dei segnali normalizzati (z-score per
    comparabilita'). xsmom = ret trailing (z), highvol = std trailing (z).
    Pesi da `weights` (es. [0.7, 0.3]). Anti-lookahead: ogni segnale usa dati <= t."""
    sigs = {}
    px = {}
    for s in symbols:
        try:
            n = max(lookback_h, vol_lookback_h) + 5
            c = fetch_live(s, lookback_h=n)["candles"]
        except Exception as e:
            print(f"  {s}: fetch fallito ({e})", file=sys.stderr)
            continue
        if c.empty:
            continue
        last = float(c.close.iloc[-1])
        if not math.isfinite(last) or last <= 0:
            continue
        px[s] = last
        needed = max((lookback_h if f == "xsmom" else vol_lookback_h)
                     for f in factors)
        if len(c) <= needed:
            continue
        parts = []
        for f, w in zip(factors, weights):
            if f == "xsmom":
                r = c.close.iloc[-1] / c.close.iloc[-1 - lookback_h] - 1.0
                parts.append(float(r) * w)
            elif f == "highvol":
                v = c.close.pct_change().iloc[-vol_lookback_h:].std()
                parts.append(float(v) * w)   # segno +: long i volatili
        value = sum(parts)
        if parts and math.isfinite(value):
            sigs[s] = value
    # normalizza per cross-section comparabilita' (z-score)
    s = pd.Series(sigs)
    if len(s) >= 3 and s.std() > 0:
        s = (s - s.mean()) / s.std()
    return s, px


def main() -> None:
    spec = load(sys.argv[1]) if len(sys.argv) > 1 else None
    if not spec or spec.get("engine") != "portfolio":
        print("uso: portfolio_paper.py <spec engine:portfolio>", file=sys.stderr)
        return
    acct = spec["id"]
    pf = spec["portfolio"]
    symbols = [s for s in paper_symbols(spec).split(",") if s]   # resolver: rispetta selection:all_perps + exclude
    lookback_h = int(pf["lookback_h"]) if "lookback_h" in pf else int(pf.get("lookbacks_h", [168])[0])
    rebalance_h = int(pf["rebalance_h"])
    gross = float(pf.get("gross", 1.0))
    multi_horizon = pf.get("lookbacks_h")        # [96,168,336] → media dei rank
    factor = pf.get("factor", "xsmom")           # xsmom | highvol | tsmom | liqimb

    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    st = state.setdefault(acct, {"equity": 10_000.0, "positions": {}, "last_rebalance_ts": "",
                                 "equity_history": []})
    vt = pf.get("vol_target")                            # overlay Moreira-Muir (opt-in)
    now = datetime.now(timezone.utc)
    print(f"portfolio paper {acct} {now:%Y-%m-%d %H:%M} UTC — equity {st['equity']:.2f}$")

    # prezzi correnti per i simboli in book + universo
    factors = pf.get("factors")                # [xsmom, highvol] → combo pesata
    if factors:
        rets, px = combo_signal(symbols, factors, pf.get("weights", [0.5, 0.5]),
                                pf.get("lookback_h", 168), pf.get("vol_lookback_h", 72))
    elif factor == "highvol":
        rets, px = vol_signal(symbols, int(pf.get("vol_lookback_h", 72)))
    elif factor == "liqimb":
        rets, px = liqimb_signal(symbols, int(pf.get("liq_lookback_d", 7)))
    else:                                        # xsmom E tsmom: ritorno trailing
        rets, px = trailing_returns(symbols, lookback_h, multi_horizon)
    price_expected = set(symbols) | set(st["positions"])
    # Prezzo osservato e segnale eleggibile sono contratti distinti. Se un perp
    # illiquido non stampa candele recenti, il mark corrente HL puo valorizzare il
    # book ma non puo inventare un segnale: ``rets`` resta invariato.
    missing_prices = price_expected - set(px)
    mark_only_symbols = set()
    if missing_prices:
        try:
            marks = {row["symbol"]: row["mark"] for row in perp_market_snapshot()}
        except Exception as exc:
            print(f"  snapshot mark HL fallita ({exc})", file=sys.stderr)
        else:
            for symbol in sorted(missing_prices & marks.keys()):
                px[symbol] = marks[symbol]
                mark_only_symbols.add(symbol)
                print(f"  {symbol}: mark HL usato solo per valorizzazione")
    price_observed = set(px) & price_expected
    write_coverage(f"{acct}-prices", price_expected, price_observed,
                   output_dir=STATE_FILE.parent / "coverage")
    missing_prices = sorted(price_expected - price_observed)
    if missing_prices:
        raise SystemExit(f"copertura prezzi incompleta: {len(price_observed)}/{len(price_expected)}; "
                         f"mancano {','.join(missing_prices[:20])}")

    rets = rets[rets.map(lambda value: math.isfinite(float(value)))]
    signal_expected = set(symbols)
    signal_observed = set(rets.index) & signal_expected
    signal_critical = factor == "liqimb"
    write_coverage(f"{acct}-signal-eligible", signal_expected, signal_observed,
                   critical=signal_critical, output_dir=STATE_FILE.parent / "coverage")
    missing_signals = sorted(signal_expected - signal_observed)
    if signal_critical and missing_signals:
        raise SystemExit(f"copertura sorgente segnale incompleta: "
                         f"{len(signal_observed)}/{len(signal_expected)}; "
                         f"mancano {','.join(missing_signals[:20])}")
    try:
        min_ratio = float(pf.get("min_signal_coverage_ratio", 0.8))
    except (TypeError, ValueError) as exc:
        raise SystemExit("min_signal_coverage_ratio non valido") from exc
    if not 0 < min_ratio <= 1:
        raise SystemExit("min_signal_coverage_ratio deve essere in (0,1]")
    min_eligible = max(3, math.ceil(len(symbols) * min_ratio))
    if len(signal_observed) < min_eligible:
        raise SystemExit(f"segnali eleggibili insufficienti: {len(signal_observed)}/{len(symbols)}; "
                         f"minimo {min_eligible} ({min_ratio:.0%})")

    due = (not st["last_rebalance_ts"] or
           now - datetime.fromisoformat(st["last_rebalance_ts"]) >= pd.Timedelta(hours=rebalance_h).to_pytimedelta())
    held_mark_only = sorted(mark_only_symbols & set(st["positions"]))
    if due and held_mark_only:
        print(f"  rebalance differito: posizioni senza candela fresca "
              f"({','.join(held_mark_only[:20])})")
        return

    # 1. mark-to-market del book esistente
    for s, pos in list(st["positions"].items()):
        if s not in px:
            continue
        new_px = px[s]
        pnl = pos["notional"] * (new_px / pos["px"] - 1.0)
        st["equity"] += pnl
        pos["notional"] *= new_px / pos["px"]   # il notional deriva col prezzo
        pos["px"] = new_px

    # 2. ribilanciamento se è ora (o book vuoto)
    if due and len(rets) < 3:
        raise SystemExit(f"rebalance dovuto ma solo {len(rets)} segnali utilizzabili")
    if due:
        m = _vol_target_multiplier(st.get("equity_history", []), vt)   # anti-lookahead: solo passato
        gross_eff = gross * m
        if vt and vt.get("enabled") and abs(m - 1.0) > 1e-6:
            print(f"  vol-target: realized->m={m:.2f} (gross {gross:.2f}->{gross_eff:.2f})")
        if factor == "tsmom":
            # sleeve trend time-series: segno del momentum, NON rank cross-section
            w = sign_weights(rets, gross=gross_eff)
        else:
            w = xs_momentum_weights(rets, long_q=float(pf.get("long_q", 0.66)),
                                    short_q=float(pf.get("short_q", 0.33)), gross=gross_eff,
                                    dollar_neutral=bool(pf.get("dollar_neutral", True)))
        target = {s: float(w[s]) * st["equity"] for s in w.index if abs(w[s]) > 1e-9}
        current = {s: st["positions"].get(s, {}).get("notional", 0.0) for s in set(target) | set(st["positions"])}
        turnover = sum(abs(target.get(s, 0.0) - current.get(s, 0.0)) for s in current)
        st["equity"] -= turnover * COST
        st["positions"] = {s: {"notional": n, "px": px[s]} for s, n in target.items() if s in px}
        st["last_rebalance_ts"] = now.isoformat()
        print(f"  REBALANCE: {len(target)} gambe, turnover {turnover:.0f}$, fee {turnover*COST:.2f}$")
        log_event({"type": "rebalance", "strategy": acct, "equity": round(st["equity"], 2),
                   "weights": {s: round(v, 4) for s, v in
                               sorted(target.items(), key=lambda kv: -abs(kv[1]))}})
    else:
        print(f"  no rebalance (prossimo tra <= {rebalance_h}h)")

    net = sum(p["notional"] for p in st["positions"].values())
    gross_now = sum(abs(p["notional"]) for p in st["positions"].values())
    # equity history per vol-target overlay (append + trim a 720 punti ~120g)
    st["equity_history"] = (st.get("equity_history", []) + [{"ts": now.isoformat(), "eq": round(st["equity"], 2)}])[-720:]
    print(f"fine: equity {st['equity']:.2f}$, gambe {len(st['positions'])}, "
          f"gross {gross_now:.0f}$, net {net:+.0f}$")
    atomic_write_text(STATE_FILE, json.dumps(state, indent=1, default=str))
    log_event({"type": "heartbeat", "strategy": acct, "equity": round(st["equity"], 2),
               "open_positions": len(st["positions"])})


if __name__ == "__main__":
    main()
