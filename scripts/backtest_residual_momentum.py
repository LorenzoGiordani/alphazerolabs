"""RESIDUAL MOMENTUM cross-sectional (Blitz-Huij-Martens 2011) — candidate Fase 2.

Il momentum "grezzo" (xsmom) e' parzialmente guidato dall'esposizione agli altri
fattori (volatilita', funding carry). Blitz et al. mostrano che ortogonalizzando il
momentum rispetto a quelle esposizioni si ottiene un "residual momentum" piu'
robusto (Sharpe piu' alto, drawdown minore, piu' persistente) perche' rimuove il
rumore fattoriale che non e' skill direzionale.

Implementazione (cross-section, identica al factor zoo per confronto diretto):
  Per ogni timestamp t, regressione OLS cross-section sui 9 asset:
      mom_i(t) = a + b1*vol_i(t) + b2*carry_i(t) + residual_i(t)
  dove mom = ritorno 168h, vol = std rolling 168h, carry = -mean funding 168h.
  residual_i(t) e' il momentum NON spiegato da vol/carry → il signal.
  Rank residual cross-section → terzile weights → dollar-neutral book.
  Rebalance 168h. P&L price-only (e' un signal direzionale, come xsmom).

Falsificazione: se lo Sharpe del residual < quello di xsmom GREZZO, ortogonalizzare
NON aiuta (allora il momentum grezzo e' gia' il meglio). Promuovi se Sharpe>1 & DSR≥0.5
E corr vs xsmom mostra che residual effettivamente differisce dal grezzo.

Uso: uv run scripts/backtest_residual_momentum.py [--months 12] [--lookback_h 168]
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


def grid_panel(symbols, months, col="close", kind="candles"):
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


def terzile_weights(signal_row, gross=1.0):
    s = signal_row.dropna()
    w = pd.Series(0.0, index=signal_row.index)
    if len(s) < 6:
        return w
    n = max(2, len(s) // 3)
    w[s.nlargest(n).index] = 0.5 / n
    w[s.nsmallest(n).index] = -0.5 / n
    g = w.abs().sum()
    return w / g * gross if g > 0 else w


def residual_signal(mom, vol, carry):
    """Panel del MOMENTUM RESIDUALE: per ogni timestamp, OLS cross-section
    mom ~ 1 + vol + carry (sugli asset non-NaN) → residual = mom - fit."""
    nr, nc = mom.shape
    out = np.full((nr, nc), np.nan)
    m_arr, v_arr, c_arr = mom.values, vol.values, carry.values
    for i in range(nr):
        m = m_arr[i]
        mask = ~(np.isnan(m) | np.isnan(v_arr[i]) | np.isnan(c_arr[i]))
        if mask.sum() < 4:  # serve almeno 4 punti per una regressione con 2 fattori+intercetta
            continue
        X = np.column_stack([np.ones(mask.sum()), v_arr[i][mask], c_arr[i][mask]])
        beta, *_ = np.linalg.lstsq(X, m[mask], rcond=None)
        out[i, mask] = m[mask] - X @ beta
    return pd.DataFrame(out, index=mom.index, columns=mom.columns)


def run_factor(bt, signal_panel, weight_fn, rebalance_h, gross=1.0):
    idx = bt.close.index
    n = len(idx)
    W = pd.DataFrame(0.0, index=idx, columns=bt.close.columns)
    turnover = pd.Series(0.0, index=idx)
    last_w = pd.Series(0.0, index=bt.close.columns)
    signal_panel = signal_panel.reindex(columns=bt.close.columns)
    first = signal_panel.dropna(how="all").index[0] if not signal_panel.dropna(how="all").empty else None
    if first is None:
        return pd.Series(1.0, index=idx), pd.Series(0.0, index=idx), 0
    start = signal_panel.index.get_loc(first) + 1
    for i in range(start, n, rebalance_h):
        w = weight_fn(signal_panel.iloc[i - 1]).reindex(bt.close.columns).fillna(0.0)
        turnover.iloc[i] = (w - last_w).abs().sum()
        last_w = w
        W.iloc[i:min(i + rebalance_h, n)] = w.to_numpy()
    port_ret = (W.shift(1) * bt.ret).sum(axis=1) - turnover * bt.cost
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
    ap.add_argument("--lookback_h", type=int, default=168)
    a = ap.parse_args()
    syms = a.symbols.split(",")
    lb = a.lookback_h

    px = grid_panel(syms, a.months)
    bt = PortfolioBacktest(px)
    ret_hourly = px.pct_change()
    fund = grid_panel(syms, a.months, "rate", "funding")

    mom = px.pct_change(lb)
    vol = ret_hourly.rolling(lb, min_periods=lb // 2).std()
    carry = (-fund).rolling(lb, min_periods=lb // 2).mean()
    resid = residual_signal(mom, vol, carry)

    # residual momentum
    eq_r, ret_r, nreb_r = run_factor(bt, resid, terzile_weights, 168)
    # raw momentum (xsmom) per confronto diretto
    eq_m, ret_m, nreb_m = run_factor(bt, mom, terzile_weights, 168)
    # highvol control (per vedere se residual diversifica anche da highvol)
    eq_v, ret_v, nreb_v = run_factor(bt, vol, terzile_weights, 168)

    beq = equal_weight_bh(px)
    br, bs, bdd = stats(beq, ret_hourly.mean(axis=1))

    trials = [ret_r.mean() / ret_r.std() if ret_r.std() else 0,
              ret_m.mean() / ret_m.std() if ret_m.std() else 0,
              ret_v.mean() / ret_v.std() if ret_v.std() else 0]
    n_trials = 3
    d_r = deflated_sharpe(ret_r, n_trials, trials)
    d_m = deflated_sharpe(ret_m, n_trials, trials)

    corr_resid_mom = float(ret_r.corr(ret_m))
    corr_resid_vol = float(ret_r.corr(ret_v))

    print(f"basket {list(px.columns)}, {len(px)} ore ({px.index.min():%Y-%m-%d} -> {px.index.max():%Y-%m-%d})")
    print(f"lookback={lb}h  rebalance=168h  gross=1.0 dollar-neutral")
    print("RESIDUAL MOMENTUM (Blitz) vs raw momentum — 12m, fee+slippage\n")
    print(f"{'fattore':<44} {'ret':>8} {'sharpe':>7} {'maxDD':>8} {'DSR':>5} {'rebal':>6} {'verdetto'}")
    print(f"{'equal-weight B&H (benchmark)':<44} {br:>+8.2%} {bs:>7.2f} {bdd:>+8.2%}")
    print("-" * 94)
    mr, msh, mdd = stats(eq_m, ret_m)
    verdict_m = "PROMUOVI" if msh > 1.0 and d_m["dsr"] >= 0.5 else ("debole" if msh > 0.3 else "falsificato")
    print(f"{'[RAW] xsmom momentum grezzo (baseline)':<44} {mr:>+8.2%} {msh:>7.2f} {mdd:>+8.2%} {d_m['dsr']:>5.2f} {nreb_m:>6} {verdict_m}")
    rr, rsh, rdd = stats(eq_r, ret_r)
    # residual e' promosso SOLO se migliora il raw (tesi Blitz) E ha edge proprio
    improves = rsh > msh
    verdict_r = "PROMUOVI" if (rsh > 1.0 and d_r["dsr"] >= 0.5 and improves) else ("debole" if rsh > 0.3 else "falsificato")
    print(f"{'[RESID] residual momentum (Blitz, orth vol+carry)':<44} {rr:>+8.2%} {rsh:>7.2f} {rdd:>+8.2%} {d_r['dsr']:>5.2f} {nreb_r:>6} {verdict_r}")
    print("-" * 94)
    print(f"ortogonalita': corr(resid, raw-mom)={corr_resid_mom:+.2f}  corr(resid, highvol)={corr_resid_vol:+.2f}")
    print(f"delta Sharpe (resid - raw) = {rsh - msh:+.2f}  -> {'Blitz aiuta (residual > raw)' if improves else 'Blitz NON aiuta (raw gia ottimo)'}")
    print(f"verdetto Fase 2: {'PROMUOVI residual-mom come candidate' if verdict_r=='PROMUOVI' else 'NON promuovere'}")


if __name__ == "__main__":
    main()
