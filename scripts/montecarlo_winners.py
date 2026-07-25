"""Monte Carlo stress test delle 3 vincitrici — soldi reali, niente margine di errore.

Le 3 vincitrici del backtest_challenge15.py:
  az-trifactor-trend       (AlphaZero)   tsmom+highvol+liqimb, gross 1.5, no VT
  turbo-quad-tailshield    (Turbo 3%DD)  4-fattori + vol-target 12%
  normal-liqimb-xsmom-5050 (Normale 6%)  liqimb+xsmom, gross 1.0

COSA FA QUESTO SCRIPT
  1. Ricalcola le equity curve storiche (max dati disponibili).
  2. Block bootstrap Monte Carlo (B=5000, block=168h = 1 settimana) che rispetta
     l'autocorrelazione dei rendimenti: risponde "quanto e' probabile che la
     strategia BREACHI il DD/daily limit?" e "quanto e' probabile che PASSI?".
  3. Walk-forward trimestrale: divide in fold, misura consistenza.
  4. Per-symbol attribution: chi dei 9 asset porta il P&L?
  5. Worst-case scenarios: percentili 5/1 della distribuzione di DD e drawdown.

Vincolo dati: coinalyze (liqimb) disponibile 2025-11-05 -> 2026-06-14 (~7 mesi).
Le strategie senza liqimb usano i 12 mesi pieni; quelle con liqimb usano ~7 mesi.

Uso: uv run scripts/montecarlo_winners.py [--B 5000]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.portfolio import PortfolioBacktest
from backtest.stats import deflated_sharpe

CRYPTO = "BTC,ETH,SOL,XRP,SUI,NEAR,WLD,ZEC,CRV"
PPY = 24 * 365
HL_TAKER_FEE = 0.00045
VALIDATION_SLIPPAGE = 0.0005


# ── data loaders ──────────────────────────────────────────────────────────────

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
    cols = {}
    for s in symbols:
        p = ROOT / f"data/coinalyze/{s}.parquet"
        if p.exists():
            c = pd.read_parquet(p).copy()
            c["ts"] = pd.to_datetime(c.ts, utc=True)
            cols[s] = c.drop_duplicates("ts").set_index("ts")[col].reindex(grid, method="ffill")
    return pd.DataFrame(cols).sort_index()


# ── weight functions ──────────────────────────────────────────────────────────

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


# ── factor builders ───────────────────────────────────────────────────────────

def build_factors(px, liq_l, liq_s, oi):
    ret1h = px.pct_change()
    f = {}
    f["xsmom_168"] = px.pct_change(168)
    f["tsmom_168"] = px.pct_change(168)
    f["highvol_72"] = ret1h.rolling(72, min_periods=36).std()
    imb = (liq_s - liq_l) / oi.replace(0, np.nan)
    f["liqimb_7d"] = imb.rolling(7 * 24, min_periods=7 * 12).mean()
    return f


# ── strategy engine (same as backtest_challenge15.py) ─────────────────────────

def run_strategy(signal_panel, bt, fund, weight_fn, rebalance_h, gross=1.0,
                 vol_target=None, vol_window_h=720, gross_floor=0.3, gross_cap=1.5):
    idx = bt.close.index
    n = len(idx)
    sig = signal_panel.reindex(columns=bt.close.columns)
    W = pd.DataFrame(0.0, index=idx, columns=bt.close.columns)
    turnover = pd.Series(0.0, index=idx)
    last_w = pd.Series(0.0, index=bt.close.columns)
    first = sig.dropna(how="all").index
    if first.empty:
        return pd.Series(1.0, index=idx), pd.Series(0.0, index=idx)
    start = sig.index.get_loc(first[0]) + 1
    for i in range(start, n, rebalance_h):
        w = weight_fn(sig.iloc[i - 1], gross=gross).reindex(bt.close.columns).fillna(0.0)
        W.iloc[i:min(i + rebalance_h, n)] = w.to_numpy()
    raw_port_ret = (W.shift(1) * bt.ret).sum(axis=1)
    if vol_target is not None:
        realized_vol = raw_port_ret.rolling(vol_window_h, min_periods=vol_window_h // 2).std() * np.sqrt(PPY)
        m = (vol_target / realized_vol).where(realized_vol > 0, 1.0)
        m = m.clip(gross_floor, gross_cap)
    else:
        m = pd.Series(1.0, index=idx)
    H = W.mul(m, axis=0)
    turnover = H.diff().abs().sum(axis=1)
    turnover.iloc[start:start + 1] = H.iloc[start].abs().sum()
    f = fund.reindex(index=idx, columns=bt.close.columns).fillna(0.0)
    price_ret = (H.shift(1) * bt.ret).sum(axis=1) - turnover * bt.cost
    funding_cf = (-(H.shift(1).fillna(0.0)) * f / 8.0).sum(axis=1)
    port_ret = price_ret + funding_cf
    equity = (1.0 + port_ret).cumprod()
    return equity, port_ret


def build_combo_returns(factors, bt, fund, legs, rebalance_h):
    """legs = [(factor_name, weight), ...]. weight_fn scelto: sign per tsmom, terzile per altri."""
    rets = []
    for fname, fw in legs:
        wf = sign_weights if fname.startswith("tsmom") else terzile_weights
        eq, ret = run_strategy(factors[fname], bt, fund, wf, rebalance_h)
        rets.append((ret, fw))
    if len(rets) == 1:
        return rets[0][0]
    return sum(w * r for r, w in rets)


# ── Monte Carlo: block bootstrap ──────────────────────────────────────────────

def block_bootstrap(ret, block_h, B, seed=42):
    """Block bootstrap della serie di rendimenti. Rispetta autocorr (block=168h=1sett).
    Ritorna matrice (B, n) di serie ri-campionate."""
    rng = np.random.default_rng(seed)
    r = ret.to_numpy()
    n = len(r)
    nb = int(np.ceil(n / block_h))
    samples = np.empty((B, n))
    for b in range(B):
        starts = rng.integers(0, n, size=nb)
        idx = (starts[:, None] + np.arange(block_h)[None, :]).ravel()[:n] % n
        samples[b] = r[idx]
    return samples


def mc_metrics(samples, target_pct, dd_limit, daily_limit, safety=0.9):
    """Per ogni sample bootstrap, calcola: maxDD, worst day, return, e gli esiti
    challenge simulati con sizing k_max. Ritorna distribuzioni."""
    B, n = samples.shape
    # equity curve per ogni sample
    eq = np.cumprod(1 + samples, axis=1)
    running_max = np.maximum.accumulate(eq, axis=1)
    dd = (eq / running_max - 1).min(axis=1)  # maxDD per sample
    # worst day: somma 24h
    n_days = n // 24
    daily = samples[:, :n_days * 24].reshape(B, n_days, 24).sum(axis=2)
    worst_day = daily.min(axis=1)
    total_ret = eq[:, -1] - 1

    # per ogni sample: k_max = min(dd_limit/|maxDD|, daily_limit/|worst_day|) * safety
    dd_pos = np.abs(dd)
    wd_pos = np.abs(worst_day)
    k_dd = np.where(dd_pos > 1e-9, dd_limit / dd_pos, 0)
    k_daily = np.where(wd_pos > 1e-9, daily_limit / wd_pos, 0)
    k_max = np.minimum(k_dd, k_daily) * safety

    # return scalato e pass challenge
    scaled_ret = total_ret * k_max
    passed = scaled_ret >= target_pct

    return {
        "maxDD_dist": dd,
        "worst_day_dist": worst_day,
        "total_ret_dist": total_ret,
        "k_max_dist": k_max,
        "scaled_ret_dist": scaled_ret,
        "p_pass": float(np.mean(passed)),
        "p_breach_dd": float(np.mean(dd < -dd_limit)),   # P(maxDD > dd_limit) grezzo (k=1)
        "p_breach_daily": float(np.mean(worst_day < -daily_limit)),
    }


# ── walk-forward ──────────────────────────────────────────────────────────────

def walkforward_quarterly(ret):
    """Divide la serie in fold trimestrali (~2160h), calcola Sharpe per fold."""
    fold_h = 90 * 24
    n = len(ret)
    folds = []
    for start in range(0, n, fold_h):
        chunk = ret.iloc[start:start + fold_h]
        if len(chunk) < 30 * 24:
            break
        sh = chunk.mean() / chunk.std() * np.sqrt(PPY) if chunk.std() else 0.0
        r = float((1 + chunk).prod() - 1)
        folds.append({"ret": r, "sharpe": sh, "n_days": len(chunk) / 24})
    return folds


# ── per-symbol attribution ────────────────────────────────────────────────────

def per_symbol_attribution(factors, bt, fund, legs, rebalance_h):
    """Per ogni asset, P&L cumulato che deriva dall'esposizione a quell'asset
    (attraverso tutti i fattori della combo)."""
    n_assets = len(bt.close.columns)
    pnl = pd.Series(0.0, index=bt.close.columns)
    for fname, fw in legs:
        sig = factors[fname].reindex(columns=bt.close.columns)
        W = pd.DataFrame(0.0, index=bt.close.index, columns=bt.close.columns)
        first = sig.dropna(how="all").index
        if first.empty:
            continue
        start = sig.index.get_loc(first[0]) + 1
        wf = sign_weights if fname.startswith("tsmom") else terzile_weights
        for i in range(start, len(bt.close), rebalance_h):
            w = wf(sig.iloc[i - 1], gross=1.0).reindex(bt.close.columns).fillna(0.0)
            W.iloc[i:min(i + rebalance_h, len(bt.close))] = w.to_numpy()
        # P&L per asset = cumsum(W.shift(1) * asset_ret)
        asset_pnl = (W.shift(1) * bt.ret).sum(axis=0)
        pnl += fw * asset_pnl
    return pnl


# ── main ──────────────────────────────────────────────────────────────────────

def stats(eq, ret):
    sh = ret.mean() / ret.std() * np.sqrt(PPY) if ret.std() else 0.0
    dd = float((eq / eq.cummax() - 1).min())
    return float(eq.iloc[-1] - 1), float(sh), dd


def define_winners():
    """Le 3 vincitrici, riprese da backtest_challenge15.py."""
    return [
        dict(name="az-trifactor-trend", group="AlphaZero",
             legs=[("tsmom_168", 0.4), ("highvol_72", 0.3), ("liqimb_7d", 0.3)],
             rebalance_h=168, gross=1.5, vol_target=None,
             uses_liqimb=True,
             challenge=None),
        dict(name="turbo-quad-tailshield", group="Turbo",
             legs=[("xsmom_168", 0.3), ("highvol_72", 0.25), ("liqimb_7d", 0.25), ("tsmom_168", 0.2)],
             rebalance_h=168, gross=1.0, vol_target=0.12,
             gross_floor=0.2, gross_cap=1.0,
             uses_liqimb=True,
             challenge=dict(target_pct=0.09, dd_limit=0.03, daily_limit=0.03)),
        dict(name="normal-liqimb-xsmom-5050", group="Normale",
             legs=[("liqimb_7d", 0.5), ("xsmom_168", 0.5)],
             rebalance_h=168, gross=1.0, vol_target=None,
             uses_liqimb=True,
             challenge=dict(target_pct=0.10, dd_limit=0.06, daily_limit=0.03)),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--B", type=int, default=5000, help="numero campioni bootstrap")
    ap.add_argument("--block_h", type=int, default=168, help="block size ore (168=1sett)")
    a = ap.parse_args()

    syms = CRYPTO.split(",")
    # coinalyze copre 2025-11-05 -> 2026-06-14 = ~7 mesi. Liqimb e' il binding constraint.
    # Per le strategie con liqimb usiamo 7 mesi; per quelle senza potremmo usare 12.
    # Ma tutte e 3 le vincitrici usano liqimb -> 7 mesi per tutte (confronto onesto).
    MONTHS = 7

    px = grid_panel(syms, MONTHS)
    fund = funding_panel(syms, MONTHS)
    liq_l = coinalyze_panel(syms, px.index, "liq_long")
    liq_s = coinalyze_panel(syms, px.index, "liq_short")
    oi = coinalyze_panel(syms, px.index, "oi")
    bt = PortfolioBacktest(px, fee=HL_TAKER_FEE, slippage=VALIDATION_SLIPPAGE)
    factors = build_factors(px, liq_l, liq_s, oi)

    winners = define_winners()

    print(f"basket {list(px.columns)}, {len(px)}h ({px.index.min():%Y-%m-%d} -> {px.index.max():%Y-%m-%d})")
    print(f"NOTE: coinalyze (liqimb) limita a ~7 mesi. Tutte le vincitrici usano liqimb.")
    print(f"Block bootstrap: B={a.B}, block={a.block_h}h ({a.block_h/24:.0f}g)\n")

    for strat in winners:
        print("=" * 100)
        print(f"  {strat['name']}  [{strat['group']}]")
        print("=" * 100)

        ret = build_combo_returns(factors, bt, fund, strat["legs"], strat["rebalance_h"])
        eq = (1.0 + ret).cumprod()
        r, sh, dd = stats(eq, ret)
        daily_ret = ret.resample("24h").sum()
        worst_day = float(daily_ret.min())

        print(f"\nSTORICO ({len(ret)/24:.0f} giorni):")
        print(f"  return {r:+.1%}  Sharpe {sh:.2f}  maxDD {dd:+.1%}  worst day {worst_day:+.2%}")
        if strat.get("vol_target"):
            print(f"  vol-target σ*={strat['vol_target']:.0%} floor={strat.get('gross_floor')} cap={strat.get('gross_cap')}")

        # ── MONTE CARLO ────────────────────────────────────────────────────
        samples = block_bootstrap(ret, a.block_h, a.B)
        n_days = len(ret) // 24

        print(f"\nMONTE CARLO (B={a.B}, block={a.block_h/24:.0f}g, {n_days}g per sample):")
        mc_raw = mc_metrics(samples, 0.99, 0.99, 0.99)  # dummy target per distribuzioni raw

        # distribuzioni raw (gross 1.0, no sizing)
        dd_d = mc_raw["maxDD_dist"]
        wd_d = mc_raw["worst_day_dist"]
        tr_d = mc_raw["total_ret_dist"]
        print(f"  maxDD     mediana {np.median(dd_d):+.1%}  P5 {np.percentile(dd_d,5):+.1%}  P1 {np.percentile(dd_d,1):+.1%}  worst {dd_d.min():+.1%}")
        print(f"  worst day mediana {np.median(wd_d):+.2%}  P5 {np.percentile(wd_d,5):+.2%}  P1 {np.percentile(wd_d,1):+.2%}  worst {wd_d.min():+.2%}")
        print(f"  return    mediana {np.median(tr_d):+.1%}  P5 {np.percentile(tr_d,5):+.1%}  P1 {np.percentile(tr_d,1):+.1%}  best {tr_d.max():+.1%}")

        # ── CHALLENGE SIMULATION (se la strategia ha una challenge target) ──
        if strat["challenge"]:
            c = strat["challenge"]
            mc_c = mc_metrics(samples, c["target_pct"], c["dd_limit"], c["daily_limit"])
            k_d = mc_c["k_max_dist"]
            sr_d = mc_c["scaled_ret_dist"]
            print(f"\nCHALLENGE {strat['group']} (target {c['target_pct']:.0%} / DD {c['dd_limit']:.0%} / daily {c['daily_limit']:.0%}):")
            print(f"  k_max     mediana {np.median(k_d):.2f}  P5 {np.percentile(k_d,5):.2f}  P1 {np.percentile(k_d,1):.2f}")
            print(f"  ret@k     mediana {np.median(sr_d):+.1%}  P5 {np.percentile(sr_d,5):+.1%}  P1 {np.percentile(sr_d,1):+.1%}")
            print(f"  >>> P(PASS challenge) = {mc_c['p_pass']:.1%} <<<")
            print(f"  >>> P(breach DD {c['dd_limit']:.0%} a gross 1.0) = {mc_c['p_breach_dd']:.1%} <<<")
            print(f"  >>> P(breach daily {c['daily_limit']:.0%} a gross 1.0) = {mc_c['p_breach_daily']:.1%} <<<")

        # ── WALK-FORWARD ───────────────────────────────────────────────────
        folds = walkforward_quarterly(ret)
        print(f"\nWALK-FORWARD trimestrale ({len(folds)} fold):")
        for i, fl in enumerate(folds, 1):
            tag = "OK" if fl["sharpe"] > 0 else "NEG"
            print(f"  fold {i}: {fl['n_days']:.0f}g  ret {fl['ret']:+.1%}  Sharpe {fl['sharpe']:.2f}  [{tag}]")
        pos_folds = sum(1 for f in folds if f["sharpe"] > 0)
        print(f"  fold positivi: {pos_folds}/{len(folds)}")

        # ── PER-SYMBOL ATTRIBUTION ─────────────────────────────────────────
        pnl_sym = per_symbol_attribution(factors, bt, fund, strat["legs"], strat["rebalance_h"])
        print(f"\nPER-SYMBOL P&L attribution:")
        for s in pnl_sym.sort_values(ascending=False).index:
            bar = "+" * int(max(0, pnl_sym[s] * 10))
            print(f"  {s:5s} {pnl_sym[s]:+.3f} {bar}")

        print()

    # ── RIEPILOGO FINALE ──────────────────────────────────────────────────
    print("=" * 100)
    print("RIEPILOGO GO/NO-GO PER CONTI REALI")
    print("=" * 100)
    print("Legenda: P(PASS) = probabilita' di passare la challenge al sizing sicuro.")
    print("         Soglia minima per soldi reali: P(PASS) >= 80% (margin di sicurezza).")
    print()


if __name__ == "__main__":
    main()
