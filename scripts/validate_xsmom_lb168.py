"""Validazione xsmom LB168 — task residui della spec docs/xsmom-lb168.md §7.

Copre i 3 test NON gia' coperti da robustness_portfolio.py (stability/bootstrap/OOS):
  [A] FUNDING NEL P&L   — A/B con/senza cashflow funding Σ_i(-w_i·r_i/8).
       Il book dollar-neutral NON azzera il funding (asimmetrico: long i forti
       con funding+, short i deboli con funding-). Quantifica il drag reale.
  [B] WALK-FORWARD FOLD — Sharpe per trimestre (4 fold non pooled): un edge
       reale e' diffuso nel tempo, non concentrato in una finestra fortunata.
  [C] PER-SIMBOLO       — contributo P&L per asset: % di asset positivi
       (edge diffuso nel cross-section, non un singolo ticker fortunato).

Costi di validazione conservativi (slippage 5bps) come robustness_portfolio.py.
Uso: uv run scripts/validate_xsmom_lb168.py [--months 12]
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
LB, REB = 168, 168


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


def run_xsmom(px, fund=None):
    """xsmom lb168/reb168 canonico. Ritorna (port_ret, W, per_asset_pnl).
    fund != None → aggiunge cashflow funding -W·r/8 per barra."""
    bt = PortfolioBacktest(px, fee=HL_TAKER_FEE, slippage=VALIDATION_SLIPPAGE)
    idx = bt.close.index
    n = len(idx)
    mom = px.pct_change(LB)
    W = pd.DataFrame(0.0, index=idx, columns=px.columns)
    turnover = pd.Series(0.0, index=idx)
    last_w = pd.Series(0.0, index=px.columns)
    first = mom.dropna(how="all").index
    start = mom.index.get_loc(first[0]) + 1 if len(first) else n
    for i in range(start, n, REB):
        w = xs_momentum_weights(mom.iloc[i - 1]).reindex(px.columns).fillna(0.0)
        turnover.iloc[i] = (w - last_w).abs().sum()
        last_w = w
        W.iloc[i:min(i + REB, n)] = w.to_numpy()
    per_asset = W.shift(1) * bt.ret          # P&L price per asset (pre-costi)
    port_ret = per_asset.sum(axis=1) - turnover * bt.cost
    if fund is not None:
        f = fund.reindex(index=idx, columns=px.columns).fillna(0.0)
        fund_cf = (-(W.shift(1).fillna(0.0)) * f / 8.0)
        per_asset = per_asset + fund_cf
        port_ret = port_ret + fund_cf.sum(axis=1)
    return port_ret, W, per_asset


def stats(ret):
    eq = (1.0 + ret).cumprod()
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
    print(f"xsmom lb{LB}/reb{REB}, basket {len(px.columns)}, {len(px)}h "
          f"({px.index.min():%Y-%m-%d} -> {px.index.max():%Y-%m-%d}), "
          f"slippage validazione {VALIDATION_SLIPPAGE:.4f}\n")

    # [A] funding A/B
    ret_nf, _, _ = run_xsmom(px)
    ret_wf, W, per_asset = run_xsmom(px, fund)
    r0, s0, d0 = stats(ret_nf)
    r1, s1, d1 = stats(ret_wf)
    drag = r0 - r1
    print("[A] FUNDING NEL P&L (A/B)")
    print(f"  {'variante':<28} {'ret':>8} {'sharpe':>7} {'maxDD':>8}")
    print(f"  {'price-only (spec §4)':<28} {r0:>+8.1%} {s0:>7.2f} {d0:>+8.1%}")
    print(f"  {'con funding cashflow':<28} {r1:>+8.1%} {s1:>7.2f} {d1:>+8.1%}")
    ann_drag = drag / (len(px) / PPY)
    print(f"  → drag funding: {drag:+.1%} sul periodo (~{ann_drag:+.1%}/anno annualizzato)")
    verdict_a = "l'edge SOPRAVVIVE al funding" if s1 > 1.0 else "il funding ERODE l'edge sotto soglia"
    print(f"  → Sharpe con funding {s1:.2f} → {verdict_a}\n")

    # [B] walk-forward fold trimestrali (con funding, il P&L onesto)
    print("[B] WALK-FORWARD PER FOLD (trimestri, P&L con funding)")
    n_folds = 4
    fold_len = len(px) // n_folds
    fold_sh = []
    for k in range(n_folds):
        seg = ret_wf.iloc[k * fold_len:(k + 1) * fold_len]
        fr, fs, fd = stats(seg)
        fold_sh.append(fs)
        print(f"  fold {k+1} ({seg.index.min():%Y-%m}→{seg.index.max():%Y-%m}): "
              f"ret {fr:+7.1%}  sharpe {fs:5.2f}  maxDD {fd:+7.1%}")
    pos_folds = sum(s > 0 for s in fold_sh)
    print(f"  → {pos_folds}/{n_folds} fold positivi, min {min(fold_sh):.2f}, "
          f"{'DIFFUSO nel tempo' if pos_folds >= 3 else 'CONCENTRATO (warning)'}\n")

    # [C] contributo per-simbolo (con funding)
    print("[C] CONTRIBUTO PER-SIMBOLO (P&L cumulato per asset)")
    contrib = per_asset.sum().sort_values(ascending=False)
    tot = contrib.sum()
    for s, c in contrib.items():
        share = c / abs(tot) if tot else 0
        print(f"  {s:<6} {c:>+8.3f}  {'█' * int(abs(share) * 20) if c > 0 else '▒' * int(abs(share) * 20)}")
    n_pos = int((contrib > 0).sum())
    print(f"  → {n_pos}/{len(contrib)} asset con contributo positivo "
          f"({'edge DIFFUSO' if n_pos >= len(contrib) * 0.55 else 'edge CONCENTRATO (warning)'})\n")

    # DSR riassuntivo sul P&L onesto (n_trials conservativo: griglia storica 48
    # di robustness_portfolio + 12 di tsmom_hmm + 4 carry + 3 residual ≈ 67)
    d = deflated_sharpe(ret_wf, 67, periods_per_year=PPY)
    print(f"riassunto: sharpe(con funding)={s1:.2f}  DSR(n_trials=67)={d['dsr']:.2f}  "
          f"maxDD={d1:+.1%}  fold positivi {pos_folds}/4  asset positivi {n_pos}/9")


if __name__ == "__main__":
    main()
