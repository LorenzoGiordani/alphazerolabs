"""Valida l'engine a portafoglio sul cross-sectional momentum (e varianti).

Confronta long-top/short-bottom dollar-neutral a varie config (lookback,
ribilanciamento, gross, neutral vs long-only) contro il basket equal-weight B&H.
Metriche da ritorni orari + DSR. Niente stop: il punto e raccogliere lo spread.

Uso: uv run scripts/backtest_portfolio.py [--symbols CSV] [--months 6]
"""
import argparse
import sys
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.portfolio import PortfolioBacktest, equal_weight_bh, xs_momentum_weights
from backtest.stats import deflated_sharpe

CRYPTO = "BTC,ETH,SOL,XRP,SUI,NEAR,WLD,ZEC,CRV"
PPY = 24 * 365


def panel(symbols, months):
    cols = {}
    for s in symbols:
        p = ROOT / f"data/candles/{s}.parquet"
        if p.exists():
            c = pd.read_parquet(p).tail(months * 30 * 24)
            cols[s] = c.set_index("ts")["close"]
    df = pd.DataFrame(cols).sort_index()
    return df[~df.index.duplicated()]


def stats(equity, ret):
    sharpe = ret.mean() / ret.std() * np.sqrt(PPY) if ret.std() else 0.0
    dd = float((equity / equity.cummax() - 1).min())
    return float(equity.iloc[-1] - 1), float(sharpe), dd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=CRYPTO)
    ap.add_argument("--months", type=int, default=6)
    a = ap.parse_args()
    px = panel(a.symbols.split(","), a.months)
    bt = PortfolioBacktest(px)
    print(f"basket {list(px.columns)}, {len(px)} ore "
          f"({px.index.min():%Y-%m-%d} → {px.index.max():%Y-%m-%d})\n")

    beq = equal_weight_bh(px)
    bret = px.pct_change().fillna(0.0).mean(axis=1)
    br, bs, bdd = stats(beq, bret)
    print(f"{'config':<46} {'ret':>8} {'sharpe':>7} {'maxDD':>8} {'DSR':>5} {'rebal':>6} {'gross':>6}")
    print(f"{'equal-weight B&H (benchmark)':<46} {br:>+8.2%} {bs:>7.2f} {bdd:>+8.2%} {'—':>5} {'—':>6} {'—':>6}")

    configs = [
        ("xs-mom dollar-neutral lb168 reb168 g1", 168, 168, dict(gross=1.0)),
        ("xs-mom dollar-neutral lb168 reb24  g1", 168, 24, dict(gross=1.0)),
        ("xs-mom dollar-neutral lb336 reb168 g1", 336, 168, dict(gross=1.0)),
        ("xs-mom dollar-neutral lb168 reb168 g2", 168, 168, dict(gross=2.0)),
        ("xs-mom long-only      lb168 reb168 g1", 168, 168, dict(gross=1.0, dollar_neutral=False)),
    ]
    rows = []
    for name, lb, reb, kw in configs:
        eq, ret, meta = bt.run(partial(xs_momentum_weights, **kw), lookback_h=lb, rebalance_h=reb)
        rows.append((name, eq, ret, meta))
    trial_srs = [r[2].mean() / r[2].std() if r[2].std() else 0 for r in rows]
    for name, eq, ret, meta in rows:
        r, sh, dd = stats(eq, ret)
        d = deflated_sharpe(ret, len(rows), trial_srs)
        gate = "PASS" if d["dsr"] >= 0.95 else "—"
        print(f"{name:<46} {r:>+8.2%} {sh:>7.2f} {dd:>+8.2%} {d['dsr']:>5.2f} "
              f"{meta['rebalances']:>6} {meta['avg_gross']:>6.2f}  {gate}")


if __name__ == "__main__":
    main()
