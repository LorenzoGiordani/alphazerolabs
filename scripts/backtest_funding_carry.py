"""FUNDING-CARRY cross-sectional (Koijen-style) — candidate Fase 2.

Carry = cio' che RICEVI tenendo una posizione long (segno). Su perp HL il funding
rate r>0 e' pagato DA long VERSO short (long paga, short incassa), quindi:
    carry di una posizione LONG = -r        (long incassa quando funding<0)
Un carry trade cross-section: LONG gli asset ad alto carry (funding piu' negativo
= longs pagati a stare = crowding short) e SHORT i basso-carry (funding positivo
= crowding long). E' il classico Koijen "carry" factor applicato al funding perp.

CRITICO: a differenza di xsmom/highvol (signal-only sul prezzo), il carry ha un
flusso di cassa vero — il funding. Un backtest di carry SENZA la cashflow funding
NON e' un carry trade, e' un funding-mean-reversion signal. Qui modelliamo ENTRAMBI:
  P&L = (W.shift(1) * ret).sum()          # price moves, anti-lookahead
       - turnover * cost                    # fee+slippage sul ribilanciamento
       + funding_cashflow                   # Σ_i (-w_i * r_i) per intervallo funding
La cashflow e' il punto: il carry harvest raccoglie funding indipendentemente
dal prezzo. Nota: il project note registra "funding non modellato nel portfolio
engine" come debito tecnico — questo script lo modella per la prima volta.

Uso: uv run scripts/backtest_funding_carry.py [--months 12] [--lookback_d 7]
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
FUND_INTERVALS_PER_YEAR = 3 * 365  # funding 3x/day su HL


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
    """Panel funding rate su griglia oraria (ffill). Funding e' 3x/day su HL."""
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


def terzile_weights(signal_row, gross=1.0):
    """Long top-terzile carry, short bottom-terzile, dollar-neutral equal-weight
    (identico al factor zoo — confronto diretto)."""
    s = signal_row.dropna()
    w = pd.Series(0.0, index=signal_row.index)
    if len(s) < 6:
        return w
    n = max(2, len(s) // 3)
    longs = s.nlargest(n).index
    shorts = s.nsmallest(n).index
    w[longs] = 0.5 / len(longs)
    w[shorts] = -0.5 / len(shorts)
    g = w.abs().sum()
    return w / g * gross if g > 0 else w


def run_carry(bt, fund_panel, carry_signal, weight_fn, rebalance_h, gross=1.0):
    """Backtest carry con funding cashflow. carry_signal: panel carry (= -funding
    mediato su lookback). Rebalance ogni rebalance_h. P&L = price + funding."""
    idx = bt.close.index
    n = len(idx)
    W = pd.DataFrame(0.0, index=idx, columns=bt.close.columns)
    turnover = pd.Series(0.0, index=idx)
    last_w = pd.Series(0.0, index=bt.close.columns)
    carry_signal = carry_signal.reindex(columns=bt.close.columns)
    first = carry_signal.dropna(how="all").index[0] if not carry_signal.dropna(how="all").empty else None
    if first is None:
        return pd.Series(1.0, index=idx), pd.Series(0.0, index=idx), 0
    start = carry_signal.index.get_loc(first) + 1
    for i in range(start, n, rebalance_h):
        w = weight_fn(carry_signal.iloc[i - 1]).reindex(bt.close.columns).fillna(0.0)
        turnover.iloc[i] = (w - last_w).abs().sum()
        last_w = w
        W.iloc[i:min(i + rebalance_h, n)] = w.to_numpy()
    price_ret = (W.shift(1) * bt.ret).sum(axis=1) - turnover * bt.cost
    # funding cashflow: Σ_i (-w_i * r_i) applicato ai soli funding interval (3x/day).
    # w_i = peso ATTIVO (W.shift(1), la posizione realmente detenuta). r = funding.
    # funding rate e' PER INTERVALLO 8h (non orario): il panel e' ffill sulla griglia
    # oraria, quindi dividere per 8 = rate orario equivalente (Σ su 8 bar = 1 intervallo).
    # BUG corretto (02/07): prima era applicato tal-qualae ogni barra -> 8x sovrastima.
    fund_aligned = fund_panel.reindex(index=idx, columns=bt.close.columns).fillna(0.0)
    fund_cashflow = (-(W.shift(1).fillna(0.0)) * fund_aligned / 8.0).sum(axis=1)
    port_ret = price_ret + fund_cashflow
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
    ap.add_argument("--lookback_d", type=int, default=7, help="finestra media funding (giorni)")
    ap.add_argument("--rebalance_h", type=int, default=8, help="cadenza ribilanciamento (h); 8= funding")
    a = ap.parse_args()
    syms = a.symbols.split(",")

    px = grid_panel(syms, a.months)
    bt = PortfolioBacktest(px)
    ret_hourly = px.pct_change()
    fund = funding_panel(syms, a.months)

    # carry = -funding (long incassa quando funding<0). Media su lookback per
    # smorzare il rumore di un singolo intervallo funding (carry sostenuto, non spike).
    lookback_h = a.lookback_d * 24
    carry_signal = (-fund).rolling(lookback_h, min_periods=lookback_h // 2).mean()

    # --- carry HARVEST (price + funding cashflow): il vero carry trade ---
    eq_c, ret_c, nreb_c = run_carry(bt, fund, carry_signal, terzile_weights, a.rebalance_h)

    # --- control: signal-only SENZA funding cashflow (funding come predittore di prezzo) ---
    # riusa run_factor-style: price-only. Costruisco un bt-price-only inline.
    eq_p, ret_p, nreb_p = run_carry(bt, fund * 0.0, carry_signal, terzile_weights, a.rebalance_h)

    # --- baseline xsmom (per ortogonalita') ---
    mom168 = px.pct_change(168)
    W_xs = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    last_w = pd.Series(0.0, index=px.columns)
    start = mom168.dropna(how="all").index[0]
    si = px.index.get_loc(start) + 1
    for i in range(si, len(px), 168):
        w = terzile_weights(mom168.iloc[i - 1]).reindex(px.columns).fillna(0.0)
        W_xs.iloc[i:min(i + 168, len(px))] = w.to_numpy()
    ret_xs = (W_xs.shift(1) * bt.ret).sum(axis=1)
    eq_xs = (1 + ret_xs).cumprod()

    beq = equal_weight_bh(px)
    br, bs, bdd = stats(beq, ret_hourly.mean(axis=1))
    xr, xs, xdd = stats(eq_xs, ret_xs)

    # DSR: contiamo i trial del carry lookback sweep come multiple-testing.
    # Conservativi: k = 3 (lookback 3/7/14g) + 1 (reb freq) = 4 trial plausibili.
    trials = [ret_c.mean() / ret_c.std() if ret_c.std() else 0,
              ret_p.mean() / ret_p.std() if ret_p.std() else 0,
              ret_xs.mean() / ret_xs.std() if ret_xs.std() else 0]
    n_trials = 4
    d_c = deflated_sharpe(ret_c, n_trials, trials)
    d_p = deflated_sharpe(ret_p, n_trials, trials)

    corr_carry_xs = float(ret_c.corr(ret_xs))
    corr_carry_bh = float(ret_c.corr(ret_hourly.mean(axis=1)))

    print(f"basket {list(px.columns)}, {len(px)} ore ({px.index.min():%Y-%m-%d} -> {px.index.max():%Y-%m-%d})")
    print(f"carry lookback={a.lookback_d}d  rebalance={a.rebalance_h}h  gross=1.0 dollar-neutral")
    print("FUNDING-CARRY cross-section — 12m, fee+slippage, funding cashflow modellato\n")
    print(f"{'fattore':<42} {'ret':>8} {'sharpe':>7} {'maxDD':>8} {'DSR':>5} {'rebal':>6} {'verdetto'}")
    print(f"{'equal-weight B&H (benchmark)':<42} {br:>+8.2%} {bs:>7.2f} {bdd:>+8.2%}")
    print(f"{'xsmom lb168 (baseline edge forte)':<42} {xr:>+8.2%} {xs:>7.2f} {xdd:>+8.2%}")
    print("-" * 92)
    cr, csh, cdd = stats(eq_c, ret_c)
    verdict_c = "PROMUOVI" if csh > 1.0 and d_c["dsr"] >= 0.5 else ("debole" if csh > 0.3 else "falsificato")
    pr, psh, pdd = stats(eq_p, ret_p)
    verdict_p = "PROMUOVI" if psh > 1.0 and d_p["dsr"] >= 0.5 else ("debole" if psh > 0.3 else "falsificato")
    print(f"{'[CARRY] carry-harvest (price+funding cf)':<42} {cr:>+8.2%} {csh:>7.2f} {cdd:>+8.2%} {d_c['dsr']:>5.2f} {nreb_c:>6} {verdict_c}")
    print(f"{'[CTRL] funding-as-signal (price only)':<42} {pr:>+8.2%} {psh:>7.2f} {pdd:>+8.2%} {d_p['dsr']:>5.2f} {nreb_p:>6} {verdict_p}")
    print("-" * 92)
    print(f"ortogonalita': corr(carry,xsmom)={corr_carry_xs:+.2f}  corr(carry,B&H)={corr_carry_bh:+.2f}")
    print(f"carry-harvest: sharpe={csh:.2f}  DSR={d_c['dsr']:.2f}  -> {verdict_c}")
    print(f"verdetto Fase 2: {'PROMUOVI come candidate challenger' if verdict_c=='PROMUOVI' else 'NON promuovere (falsificato/debole)'}")


if __name__ == "__main__":
    main()
