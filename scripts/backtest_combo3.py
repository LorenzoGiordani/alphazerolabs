"""COMBO3 — 10ª strategia: blend a livello di BOOK di 3 edge.

  xsmom lb168   (cross-sectional momentum, dollar-neutral)  — edge core
  highvol lb72  (risk premium volatilita', dollar-neutral)  — 2° edge, corr +0.28
  tsmom lb168   (time-series momentum sign-based, puo' essere net-long) —
                sleeve DIREZIONALE trend (promossa 04/07, gate HMM falsificato)

Differenza dalle combo esistenti (xsmom-highvol-combo blend di SEGNALI z-scored
in un book unico): qui blend di PESI: W = a·W_xs + b·W_hv + c·W_ts, ribilancio
24h, turnover calcolato sul book combinato (fee oneste, il netting interno tra
sleeve riduce il turnover reale). La sleeve tsmom aggiunge esposizione
direzionale nei trend che il dollar-neutral puro lascia sul tavolo.

P&L: price + funding cashflow (-W·r/8). Costi validazione (slippage 5bps).
Sweep blend: griglia pesi (passo 0.1, min 0.2 per sleeve) — tutti trial nel DSR.
Uso: uv run scripts/backtest_combo3.py [--months 12]
Promozione: Sharpe > 1.0 AND DSR >= 0.5 e valore aggiunto vs combo 2-sleeve.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.portfolio import PortfolioBacktest, xs_momentum_weights
from backtest.stats import deflated_sharpe

CRYPTO = "BTC,ETH,SOL,XRP,SUI,NEAR,WLD,ZEC,CRV"
PPY = 24 * 365
HL_TAKER_FEE = 0.00045
VALIDATION_SLIPPAGE = 0.0005


def grid_panel(symbols, months, col="close", kind="candles"):
    btc = pd.read_parquet(ROOT / "data/candles/BTC.parquet").tail(months * 30 * 24)
    grid = pd.to_datetime(btc.ts, utc=True)
    cols = {}
    for s in symbols:
        p = ROOT / f"data/{kind}/{s}.parquet"
        if p.exists():
            c = pd.read_parquet(p).copy()
            c["ts"] = pd.to_datetime(c.ts, utc=True)
            if col in c.columns:
                cols[s] = (c.drop_duplicates("ts").set_index("ts")[col]
                           .reindex(grid, method="ffill"))
    return pd.DataFrame(cols).sort_index()


def funding_panel(symbols, months):
    btc = pd.read_parquet(ROOT / "data/candles/BTC.parquet").tail(months * 30 * 24)
    grid = pd.to_datetime(btc.ts, utc=True)
    cols = {}
    for s in symbols:
        p = ROOT / f"data/funding/{s}.parquet"
        if p.exists():
            c = pd.read_parquet(p).copy()
            c["ts"] = pd.to_datetime(c.ts, utc=True)
            cols[s] = c.drop_duplicates("ts").set_index("ts")["rate"].reindex(grid, method="ffill")
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


def sign_weights(signal_row, gross=1.0):
    s = signal_row.dropna()
    w = pd.Series(0.0, index=signal_row.index)
    longs, shorts = s[s > 0].index, s[s < 0].index
    if len(longs):
        w[longs] = 0.5 / len(longs)
    if len(shorts):
        w[shorts] = -0.5 / len(shorts)
    g = w.abs().sum()
    return w / g * gross if g > 0 else w


def sleeve_weights(px):
    """Pesi target per barra delle 3 sleeve (ognuna alla PROPRIA cadenza:
    xsmom/highvol 168h, tsmom 24h). Ritorna dict di DataFrame pesi."""
    idx = px.index
    n = len(idx)
    mom = px.pct_change(168)
    hv = px.pct_change().rolling(72, min_periods=36).std()
    out = {}
    for name, sig, wfn, reb in (("xs", mom, xs_momentum_weights, 168),
                                ("hv", hv, terzile_weights, 168),
                                ("ts", mom, sign_weights, 24)):
        W = pd.DataFrame(0.0, index=idx, columns=px.columns)
        first = sig.dropna(how="all").index
        start = sig.index.get_loc(first[0]) + 1 if len(first) else n
        for i in range(start, n, reb):
            w = wfn(sig.iloc[i - 1]).reindex(px.columns).fillna(0.0)
            W.iloc[i:min(i + reb, n)] = w.to_numpy()
        out[name] = W
    return out


def run_blend(bt, sleeves, fund, blend):
    """W = Σ blend_k · W_k, turnover sul book combinato ai bar dove W cambia."""
    W = sum(blend[k] * sleeves[k] for k in blend)
    dW = W.diff().abs().sum(axis=1).fillna(0.0)
    turnover = dW.where(dW > 1e-12, 0.0)
    price_ret = (W.shift(1) * bt.ret).sum(axis=1) - turnover * bt.cost
    f = fund.reindex(index=bt.close.index, columns=bt.close.columns).fillna(0.0)
    port_ret = price_ret + (-(W.shift(1).fillna(0.0)) * f / 8.0).sum(axis=1)
    eq = (1.0 + port_ret).cumprod()
    return eq, port_ret, int((turnover > 0).sum())


def stats(eq, ret):
    sh = ret.mean() / ret.std() * np.sqrt(PPY) if ret.std() else 0.0
    dd = float((eq / eq.cummax() - 1).min())
    return float(eq.iloc[-1] - 1), float(sh), dd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12)
    a = ap.parse_args()
    syms = CRYPTO.split(",")
    px = grid_panel(syms, a.months)
    fund = funding_panel(syms, a.months)
    bt = PortfolioBacktest(px, fee=HL_TAKER_FEE, slippage=VALIDATION_SLIPPAGE)
    sleeves = sleeve_weights(px)

    # singole sleeve (riferimento)
    print(f"basket {len(px.columns)}, {len(px)}h ({px.index.min():%Y-%m-%d} -> {px.index.max():%Y-%m-%d}), slippage 5bps, funding modellato\n")
    print(f"{'book':<26} {'ret':>8} {'sharpe':>7} {'maxDD':>8} {'DSR':>5}  note")
    singles = {}
    for k, label in (("xs", "xsmom lb168/reb168"), ("hv", "highvol 72/168"), ("ts", "tsmom lb168/reb24")):
        eq, ret, _ = run_blend(bt, sleeves, fund, {k: 1.0})
        singles[k] = ret
        r, sh, dd = stats(eq, ret)
        print(f"{label:<26} {r:>+8.1%} {sh:>7.2f} {dd:>+8.1%}")
    # combo 2-sleeve esistente (baseline da battere, stessa costruzione book-level)
    eq2, ret2, _ = run_blend(bt, sleeves, fund, {"xs": 0.7, "hv": 0.3})
    r2, s2, d2 = stats(eq2, ret2)
    print(f"{'combo2 xs70/hv30 (baseline)':<26} {r2:>+8.1%} {s2:>7.2f} {d2:>+8.1%}")
    print("-" * 78)

    # sweep griglia blend 3 sleeve (passo .1, min .2 ciascuna)
    grid = []
    for x in np.arange(0.2, 0.61, 0.1):
        for h in np.arange(0.2, 0.61, 0.1):
            t = 1.0 - x - h
            if 0.19 <= t <= 0.61:
                grid.append((round(x, 1), round(h, 1), round(t, 1)))
    results = {}
    for x, h, t in grid:
        eq, ret, nreb = run_blend(bt, sleeves, fund, {"xs": x, "hv": h, "ts": t})
        results[(x, h, t)] = (eq, ret, nreb)
    n_trials = len(results) + 4  # griglia + le 3 sleeve + combo2
    trial_srs = [r[1].mean() / r[1].std() if r[1].std() else 0.0 for r in results.values()]
    best = None
    for (x, h, t), (eq, ret, nreb) in sorted(results.items()):
        r, sh, dd = stats(eq, ret)
        d = deflated_sharpe(ret, n_trials, trial_srs)
        flag = " ***" if sh > s2 and dd > d2 else ""
        print(f"combo3 xs{x:.0%}/hv{h:.0%}/ts{t:.0%}     {r:>+8.1%} {sh:>7.2f} {dd:>+8.1%} {d['dsr']:>5.2f}{flag}")
        if best is None or sh > best[1]:
            best = ((x, h, t), sh, dd, d["dsr"])
    print("-" * 78)
    (x, h, t), sh, dd, dsr = best
    print(f"best: xs{x:.0%}/hv{h:.0%}/ts{t:.0%} sharpe={sh:.2f} maxDD={dd:+.1%} DSR={dsr:.2f} "
          f"vs combo2 sharpe={s2:.2f} maxDD={d2:+.1%}")
    verdict = "PROMUOVI" if sh > 1.0 and dsr >= 0.5 and sh >= s2 else "NON promuovere"
    print(f"verdetto: {verdict} (*** = batte combo2 su Sharpe E maxDD)")


if __name__ == "__main__":
    main()
