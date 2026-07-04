"""TSMOM regime-gated HMM — 3ª candidata Fase 2.

Tesi: il time-series momentum (long asset con mom>0, short mom<0, equal-weight
per gamba) perde nel chop (lezione walkforward). Un gate di regime HMM
(precompute_hmm.py, cache data/hmm/, walk-forward anti-lookahead) dovrebbe
tenere il book acceso solo nei regimi trending e alzare Sharpe/DSR.

Gate testati (A/B espliciti, tutti contati come trial nel DSR):
  none      tsmom-neutral sempre acceso (baseline)
  btc       book acceso solo se regime BTC = trending
  or        acceso se BTC O ETH trending
  and       acceso solo se BTC E ETH trending

P&L onesto: il book tsmom puo' essere net-long (se tutti i mom>0) → il funding
NON si azzera. Modellato come cashflow Σ_i(-w_i·r_i/8) per barra (rate HL
per-intervallo 8h, ffill orario → /8; vedi bug carry 02/07).

Uso: uv run scripts/backtest_tsmom_hmm.py [--months 12] [--rebalance_h 24]
Promozione (soglia zoo): Sharpe > 1.0 AND DSR >= 0.5. Ortogonalita' vs xsmom.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.portfolio import PortfolioBacktest, equal_weight_bh
from backtest.stats import deflated_sharpe

CRYPTO = "BTC,ETH,SOL,XRP,SUI,NEAR,WLD,ZEC,CRV"
PPY = 24 * 365
LOOKBACKS = (96, 168, 336)
GATES = ("none", "btc", "or", "and")


def grid_panel(symbols, months, col="close", kind="candles"):
    """Panel su griglia oraria BTC (24/7). ffill per session-based (come lo zoo)."""
    btc = pd.read_parquet(ROOT / "data/candles/BTC.parquet").tail(months * 30 * 24)
    grid = pd.to_datetime(btc.ts, utc=True)
    cols = {}
    for s in symbols:
        p = ROOT / f"data/{kind}/{s}.parquet"
        if not p.exists():
            continue
        c = pd.read_parquet(p).copy()
        c["ts"] = pd.to_datetime(c.ts, utc=True)
        if col in c.columns:
            cols[s] = c.drop_duplicates("ts").set_index("ts")[col].reindex(grid, method="ffill")
    return pd.DataFrame(cols).sort_index()


def funding_panel(symbols, months):
    btc = pd.read_parquet(ROOT / "data/candles/BTC.parquet").tail(months * 30 * 24)
    grid = pd.to_datetime(btc.ts, utc=True)
    cols = {}
    for s in symbols:
        p = ROOT / f"data/funding/{s}.parquet"
        if not p.exists():
            continue
        c = pd.read_parquet(p).copy()
        c["ts"] = pd.to_datetime(c.ts, utc=True)
        cols[s] = c.drop_duplicates("ts").set_index("ts")["rate"].reindex(grid, method="ffill")
    return pd.DataFrame(cols).sort_index()


def regime_series(sym, grid):
    """Regime 0/1 dalla cache sparsa (una riga per transizione) → ffill su griglia.
    Anti-lookahead: la label a ts vale DA ts in poi (decodifica su dati ≤ ts)."""
    p = ROOT / f"data/hmm/{sym}.parquet"
    r = pd.read_parquet(p)
    r["ts"] = pd.to_datetime(r.ts, utc=True)
    s = r.drop_duplicates("ts").set_index("ts")["regime"].reindex(grid, method="ffill")
    return s.fillna(0).astype(int)


def sign_weights(signal_row, gross=1.0):
    """Long mom>0, short mom<0, equal-weight per gamba (TSMOM-neutral, come zoo)."""
    s = signal_row.dropna()
    w = pd.Series(0.0, index=signal_row.index)
    longs = s[s > 0].index
    shorts = s[s < 0].index
    if len(longs):
        w[longs] = 0.5 / len(longs)
    if len(shorts):
        w[shorts] = -0.5 / len(shorts)
    g = w.abs().sum()
    return w / g * gross if g > 0 else w


def run_gated(bt, mom_panel, gate, fund_panel, rebalance_h):
    """Backtest tsmom con gate 0/1 (flat quando gate=0). Anti-lookahead: segnale e
    gate letti a i-1, pesi applicati da i (shift(1) nel P&L)."""
    idx = bt.close.index
    n = len(idx)
    W = pd.DataFrame(0.0, index=idx, columns=bt.close.columns)
    turnover = pd.Series(0.0, index=idx)
    last_w = pd.Series(0.0, index=bt.close.columns)
    first = mom_panel.dropna(how="all").index
    if first.empty:
        return pd.Series(1.0, index=idx), pd.Series(0.0, index=idx), 0
    start = mom_panel.index.get_loc(first[0]) + 1
    for i in range(start, n, rebalance_h):
        if gate is not None and gate.iloc[i - 1] == 0:
            w = pd.Series(0.0, index=bt.close.columns)
        else:
            w = sign_weights(mom_panel.iloc[i - 1]).reindex(bt.close.columns).fillna(0.0)
        turnover.iloc[i] = (w - last_w).abs().sum()
        last_w = w
        W.iloc[i:min(i + rebalance_h, n)] = w.to_numpy()
    price_ret = (W.shift(1) * bt.ret).sum(axis=1) - turnover * bt.cost
    fund_aligned = fund_panel.reindex(index=idx, columns=bt.close.columns).fillna(0.0)
    fund_cf = (-(W.shift(1).fillna(0.0)) * fund_aligned / 8.0).sum(axis=1)
    port_ret = price_ret + fund_cf
    eq = (1.0 + port_ret).cumprod()
    return eq, port_ret, int((turnover > 0).sum())


def stats(eq, ret):
    sharpe = ret.mean() / ret.std() * np.sqrt(PPY) if ret.std() else 0.0
    dd = float((eq / eq.cummax() - 1).min())
    return float(eq.iloc[-1] - 1), float(sharpe), dd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=CRYPTO)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--rebalance_h", type=int, default=24)
    a = ap.parse_args()
    syms = a.symbols.split(",")

    px = grid_panel(syms, a.months)
    bt = PortfolioBacktest(px)
    fund = funding_panel(syms, a.months)
    reg_btc = regime_series("BTC", px.index)
    reg_eth = regime_series("ETH", px.index)
    gates = {"none": None, "btc": reg_btc,
             "or": ((reg_btc + reg_eth) > 0).astype(int),
             "and": ((reg_btc * reg_eth) > 0).astype(int)}

    # baseline xsmom (ortogonalita')
    mom168 = px.pct_change(168)
    from backtest.portfolio import xs_momentum_weights
    W_xs = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    start = mom168.dropna(how="all").index[0]
    si = px.index.get_loc(start) + 1
    for i in range(si, len(px), 168):
        w = xs_momentum_weights(mom168.iloc[i - 1]).reindex(px.columns).fillna(0.0)
        W_xs.iloc[i:min(i + 168, len(px))] = w.to_numpy()
    ret_xs = (W_xs.shift(1) * bt.ret).sum(axis=1)
    ret_bh = px.pct_change().fillna(0.0).mean(axis=1)

    # sweep completo: ogni (gate, lookback) e' un trial per il DSR
    results = {}
    for lb in LOOKBACKS:
        mom = px.pct_change(lb)
        for g in GATES:
            eq, ret, nreb = run_gated(bt, mom, gates[g], fund, a.rebalance_h)
            results[(g, lb)] = (eq, ret, nreb)
    n_trials = len(results)
    trial_srs = [r[1].mean() / r[1].std() if r[1].std() else 0.0 for r in results.values()]

    beq = equal_weight_bh(px)
    br, bs, bdd = stats(beq, ret_bh)
    xr, xsh, xdd = stats((1 + ret_xs).cumprod(), ret_xs)
    print(f"basket {list(px.columns)}, {len(px)} ore ({px.index.min():%Y-%m-%d} -> {px.index.max():%Y-%m-%d})")
    print(f"rebalance={a.rebalance_h}h  gross=1.0  funding cashflow modellato  "
          f"regime trending: BTC {reg_btc.mean():.0%}, ETH {reg_eth.mean():.0%}\n")
    print(f"{'variante':<28} {'ret':>8} {'sharpe':>7} {'maxDD':>8} {'DSR':>5} {'rebal':>6} {'corr_xs':>8}  verdetto")
    print(f"{'equal-weight B&H':<28} {br:>+8.2%} {bs:>7.2f} {bdd:>+8.2%}")
    print(f"{'xsmom lb168 (baseline)':<28} {xr:>+8.2%} {xsh:>7.2f} {xdd:>+8.2%}")
    print("-" * 100)
    best = None
    for (g, lb), (eq, ret, nreb) in results.items():
        r, sh, dd = stats(eq, ret)
        d = deflated_sharpe(ret, n_trials, trial_srs)
        corr = float(ret.corr(ret_xs))
        verdict = "PROMUOVI" if sh > 1.0 and d["dsr"] >= 0.5 else ("debole" if sh > 0.3 else "falsificato")
        print(f"{f'tsmom lb{lb} gate={g}':<28} {r:>+8.2%} {sh:>7.2f} {dd:>+8.2%} "
              f"{d['dsr']:>5.2f} {nreb:>6} {corr:>+8.2f}  {verdict}")
        if verdict == "PROMUOVI" and (best is None or sh > best[1]):
            best = ((g, lb), sh, d["dsr"])
    print("-" * 100)
    if best:
        (g, lb), sh, dsr = best
        print(f"verdetto Fase 2: PROMUOVI tsmom lb{lb} gate={g} (sharpe={sh:.2f}, DSR={dsr:.2f})")
    else:
        print("verdetto Fase 2: NON promuovere (nessuna variante supera Sharpe>1 & DSR>=0.5)")


if __name__ == "__main__":
    main()
