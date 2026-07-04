"""Factor zoo 2 — caccia alla 10ª strategia (fattori MAI testati a portafoglio).

Il primo zoo (backtest_factor_zoo.py) ha testato momentum/reversal/vol/flow/OI/
top-trader. Qui i fattori rimasti sfruttabili coi dati gia' in repo:

  SKEW      skewness realizzata dei ritorni orari (lottery preference:
            letteratura = short positive-skew, long negative-skew)
  MAXRET    max ritorno giornaliero trailing (MAX factor di Bali-Cakici-Whitelaw:
            short i lottery ticket con spike recente)
  AMIHUD    illiquidita' Amihud |ret|/dollar-volume (premio di illiquidita':
            long illiquidi, short liquidi)
  LIQIMB    sbilancio liquidazioni cross-section da Coinalyze daily
            ((liq_short-liq_long)/oi: long dove shortano gli short squeezati —
            versione PORTFOLIO del segnale per-simbolo liq_imbalance)

Convenzione segno: segnale costruito con premio atteso POSITIVO da letteratura.
Sharpe fortemente negativo = fattore invertito e' il candidato (lezione LOW-VOL
→ HIGH-VOL del 26/06); l'inversione conta come trial nel DSR (n_trials = 2x).

P&L onesto: funding cashflow modellato (-W·r/8). Costi validazione (slip 5bps).
Uso: uv run scripts/backtest_factor_zoo2.py [--months 12] [--rebalance_h 168]
Promozione: Sharpe > 1.0 AND DSR >= 0.5, ortogonalita' vs xsmom E highvol.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.portfolio import PortfolioBacktest, equal_weight_bh, xs_momentum_weights
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


def coinalyze_panel(symbols, grid, col):
    """Panel daily Coinalyze → ffill su griglia oraria (dato daily noto a fine giorno)."""
    cols = {}
    for s in symbols:
        p = ROOT / f"data/coinalyze/{s}.parquet"
        if p.exists():
            c = pd.read_parquet(p).copy()
            c["ts"] = pd.to_datetime(c.ts, utc=True)
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


def run_factor(bt, sig, fund, rebalance_h):
    idx = bt.close.index
    n = len(idx)
    sig = sig.reindex(columns=bt.close.columns)
    W = pd.DataFrame(0.0, index=idx, columns=bt.close.columns)
    turnover = pd.Series(0.0, index=idx)
    last_w = pd.Series(0.0, index=bt.close.columns)
    first = sig.dropna(how="all").index
    if first.empty:
        return pd.Series(1.0, index=idx), pd.Series(0.0, index=idx), 0
    start = sig.index.get_loc(first[0]) + 1
    for i in range(start, n, rebalance_h):
        w = terzile_weights(sig.iloc[i - 1]).reindex(bt.close.columns).fillna(0.0)
        turnover.iloc[i] = (w - last_w).abs().sum()
        last_w = w
        W.iloc[i:min(i + rebalance_h, n)] = w.to_numpy()
    price_ret = (W.shift(1) * bt.ret).sum(axis=1) - turnover * bt.cost
    f = fund.reindex(index=idx, columns=bt.close.columns).fillna(0.0)
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
    ap.add_argument("--rebalance_h", type=int, default=168)
    a = ap.parse_args()
    syms = CRYPTO.split(",")
    px = grid_panel(syms, a.months)
    vol = grid_panel(syms, a.months, col="volume")
    fund = funding_panel(syms, a.months)
    bt = PortfolioBacktest(px, fee=HL_TAKER_FEE, slippage=VALIDATION_SLIPPAGE)
    ret1h = px.pct_change()
    ret24 = px.pct_change(24)

    # ── segnali (segno = premio atteso positivo da letteratura) ────────────
    signals = {}
    for lb in (168, 336):
        # SKEW: long negative-skew, short positive-skew → segnale = -skew
        signals[f"skew{lb}"] = -ret1h.rolling(lb, min_periods=lb // 2).skew()
    for d in (7, 30):
        # MAX: short chi ha appena stampato lo spike giornaliero max → -max
        signals[f"maxret{d}d"] = -ret24.rolling(d * 24, min_periods=d * 12).max()
    dollar_vol = px * vol
    illiq = (ret1h.abs() / dollar_vol.replace(0, np.nan))
    for lb in (168, 336):
        # AMIHUD: long illiquidi (premio) → segnale = illiq media
        signals[f"amihud{lb}"] = illiq.rolling(lb, min_periods=lb // 2).mean()
    liq_l = coinalyze_panel(syms, px.index, "liq_long")
    liq_s = coinalyze_panel(syms, px.index, "liq_short")
    oi = coinalyze_panel(syms, px.index, "oi")
    imb = (liq_s - liq_l) / oi.replace(0, np.nan)
    for d in (7, 14):
        # LIQIMB: long dove gli short vengono squeezati (follow, lezione 14/06)
        signals[f"liqimb{d}d"] = imb.rolling(d * 24, min_periods=d * 12).mean()

    # baseline per ortogonalita'
    mom168 = px.pct_change(168)
    W_xs = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    si = px.index.get_loc(mom168.dropna(how="all").index[0]) + 1
    for i in range(si, len(px), 168):
        w = xs_momentum_weights(mom168.iloc[i - 1]).reindex(px.columns).fillna(0.0)
        W_xs.iloc[i:min(i + 168, len(px))] = w.to_numpy()
    ret_xs = (W_xs.shift(1) * bt.ret).sum(axis=1)
    hv = ret1h.rolling(72, min_periods=36).std()
    eq_hv, ret_hv, _ = run_factor(bt, hv, fund, 168)

    results = {}
    for name, sig in signals.items():
        results[name] = run_factor(bt, sig, fund, a.rebalance_h)
    # ogni fattore conta doppio (segnale + eventuale inversione valutata a vista)
    n_trials = len(results) * 2
    trial_srs = [r[1].mean() / r[1].std() if r[1].std() else 0.0 for r in results.values()]

    beq = equal_weight_bh(px)
    br, bs, bdd = stats(beq, ret1h.mean(axis=1))
    print(f"basket {list(px.columns)}, {len(px)}h ({px.index.min():%Y-%m-%d} -> {px.index.max():%Y-%m-%d})")
    print(f"rebalance={a.rebalance_h}h  slippage 5bps  funding modellato  n_trials DSR={n_trials}\n")
    print(f"{'fattore':<14} {'ret':>8} {'sharpe':>7} {'maxDD':>8} {'DSR':>5} {'corr_xs':>8} {'corr_hv':>8}  verdetto")
    print(f"{'B&H equal-w':<14} {br:>+8.1%} {bs:>7.2f} {bdd:>+8.1%}")
    print("-" * 92)
    for name, (eq, ret, nreb) in results.items():
        r, sh, dd = stats(eq, ret)
        d = deflated_sharpe(ret, n_trials, trial_srs)
        cx = float(ret.corr(ret_xs))
        ch = float(ret.corr(ret_hv))
        verdict = ("PROMUOVI" if sh > 1.0 and d["dsr"] >= 0.5
                   else "INVERTI?" if sh < -1.0
                   else "debole" if abs(sh) > 0.3 else "morto")
        print(f"{name:<14} {r:>+8.1%} {sh:>7.2f} {dd:>+8.1%} {d['dsr']:>5.2f} {cx:>+8.2f} {ch:>+8.2f}  {verdict}")
    print("-" * 92)
    print("nota: INVERTI? = testare il segnale col segno opposto (conta come trial)")


if __name__ == "__main__":
    main()
