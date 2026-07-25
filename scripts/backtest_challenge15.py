"""Backtest 15 strategie per 3 contesti challenge (AlphaZero / Prop Turbo / Prop Normale).

Costruisce 15 strategie componendo i 4 edge validati nel progetto
(tsmom, xsmom, highvol, liqimb) con configurazioni di sizing/vol-target
calibrate per i 3 vincoli di challenge:

  AlphaZero  : nessun limite      -> massimizza Sharpe/return, gross aggressivo
  Prop Turbo : 9% target / 3% DD  -> Calmar >= 3:1, vol-target overlay obbligato
  Prop Norm. : 10% target / 6% DD -> Calmar >= 1.67:1, vol-target leggero

METODOLOGIA DELLA CHALLENGE
  La challenge e' un problema di SIZING, non di edge. Data l'equity curve di una
  strategia (return%, maxDD%, peggior giorno%), il sizing massimo che rispetta i
  vincoli e':
      k_max = min(dd_limit / maxDD, daily_limit / |worst_day|) * safety_margin
  La strategia PASSA se k_max * expected_return >= target in tempo ragionevole.
  Se k_max < 1 la strategia va de-leveraged per sopravvivere; se k_max e' cosi'
  basso che il return annuo < target, FAIL (non c'e' sizing utile).

ONESTA'
  - Numeri reali dal backtest, nessuno inventato.
  - DSR con n_trials=15 (correzione multiple-testing).
  - Le strategie Turbo potrebbero NON passarne nessuna (3% DD e' brutale).
  - I risultati FAIL sono validi e documentati.

Uso: uv run scripts/backtest_challenge15.py [--months 12]
"""
from __future__ import annotations

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
HL_TAKER_FEE = 0.00045
VALIDATION_SLIPPAGE = 0.0005


# ── data loaders (pattern da backtest_factor_zoo2.py) ─────────────────────────

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
    """Cross-sectional: long top-terzile, short bottom-terzile (dollar-neutral)."""
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
    """Time-series: long signal>0, short signal<0 (NON dollar-neutral, direzionale)."""
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

def build_factors(px, vol, liq_l, liq_s, oi):
    """Costruisce i 4 pannelli-segnale dai dati raw."""
    ret1h = px.pct_change()
    f = {}
    # xsmom: cross-sectional momentum (ranking, relativo)
    f["xsmom_168"] = px.pct_change(168)
    f["xsmom_336"] = px.pct_change(336)
    # tsmom: time-series momentum (direzionale, segno del ritorno)
    f["tsmom_168"] = px.pct_change(168)
    f["tsmom_96"] = px.pct_change(96)
    f["tsmom_336"] = px.pct_change(336)
    # highvol: risk premium, long i piu volatili
    f["highvol_72"] = ret1h.rolling(72, min_periods=36).std()
    f["highvol_168"] = ret1h.rolling(168, min_periods=84).std()
    # liqimb: squeeze-follow (long dove gli short vengono squeezati)
    imb = (liq_s - liq_l) / oi.replace(0, np.nan)
    f["liqimb_7d"] = imb.rolling(7 * 24, min_periods=7 * 12).mean()
    f["liqimb_14d"] = imb.rolling(14 * 24, min_periods=14 * 12).mean()
    return f


# ── backtest core (custom signal panel + rebalance + funding) ─────────────────

def run_strategy(signal_panel, bt, fund, weight_fn, rebalance_h, gross=1.0,
                 vol_target=None, vol_window_h=720, gross_floor=0.3, gross_cap=1.5,
                 corr_gate=False, corr_window_d=7, corr_threshold=0.8):
    """Backtest un fattore/combo su pannello segnale custom.

    weight_fn       : terzile_weights (xsmom/highvol/liqimb) o sign_weights (tsmom)
    vol_target      : σ* annualizzato per overlay Moreira-Muir (None = off)
    corr_gate       : se True, riduce il gross quando la corr media basket > corr_threshold
    Ritorna: equity, port_ret, meta
    """
    idx = bt.close.index
    n = len(idx)
    sig = signal_panel.reindex(columns=bt.close.columns)
    W = pd.DataFrame(0.0, index=idx, columns=bt.close.columns)
    turnover = pd.Series(0.0, index=idx)
    last_w = pd.Series(0.0, index=bt.close.columns)
    first = sig.dropna(how="all").index
    if first.empty:
        return pd.Series(1.0, index=idx), pd.Series(0.0, index=idx), {}
    start = sig.index.get_loc(first[0]) + 1

    # ── matrice pesi raw (anti-lookahead: decisi a t, applicati t+1) ──────
    for i in range(start, n, rebalance_h):
        w = weight_fn(sig.iloc[i - 1], gross=gross).reindex(bt.close.columns).fillna(0.0)
        W.iloc[i:min(i + rebalance_h, n)] = w.to_numpy()

    # ── vol-target overlay (Moreira-Muir): scala gross inverso a vol realizzata ──
    raw_port_ret = (W.shift(1) * bt.ret).sum(axis=1)
    if vol_target is not None:
        realized_vol = raw_port_ret.rolling(vol_window_h, min_periods=vol_window_h // 2).std() * np.sqrt(PPY)
        m = (vol_target / realized_vol).where(realized_vol > 0, 1.0)
        m = m.clip(gross_floor, gross_cap)
    else:
        m = pd.Series(1.0, index=idx)

    # ── correlation gate: de-risk quando il basket sincronizza ─────────────
    # Computazione onesta della corr media a sliding window: ricalcolo la matrice
    # di correlazione su griglia giornaliera (8640h / 24 = 360 punti, fattibile).
    # L'approccio column-wise di pandas.rolling().apply() non puo' calcolare corr
    # cross-asset, quindi batch-manuale su griglia giornaliera poi reindex hourly.
    if corr_gate:
        asset_ret = bt.ret
        win = corr_window_d * 24
        # ricalcola la corr media su griglia giornaliera (~360 punti su 12m, fattibile)
        # per evitare KeyError su timestamp mismatch, itero su posizioni intere ogni 24h
        n_ar = len(asset_ret)
        corr_vals = np.full(n_ar, np.nan)
        for end in range(win, n_ar, 24):
            window = asset_ret.iloc[end - win:end]
            if window.shape[0] < 48:
                continue
            c = window.corr()
            if c.empty:
                continue
            mask = ~np.eye(c.shape[0], dtype=bool)
            corr_vals[end] = float(np.nanmean(c.to_numpy()[mask]))
        corr_series = pd.Series(corr_vals, index=asset_ret.index).ffill().fillna(0.0)
        gate = pd.Series(np.where(corr_series > corr_threshold, 0.5, 1.0), index=idx)
        m = m * gate

    # ── pesi effettivi + funding + turnover ────────────────────────────────
    H = W.mul(m, axis=0)
    turnover = H.diff().abs().sum(axis=1)
    turnover.iloc[start:start + 1] = H.iloc[start].abs().sum()
    f = fund.reindex(index=idx, columns=bt.close.columns).fillna(0.0)
    price_ret = (H.shift(1) * bt.ret).sum(axis=1) - turnover * bt.cost
    funding_cf = (-(H.shift(1).fillna(0.0)) * f / 8.0).sum(axis=1)
    port_ret = price_ret + funding_cf
    equity = (1.0 + port_ret).cumprod()

    meta = {
        "rebalances": int(((W.abs().sum(axis=1) > 0).astype(int).diff() == 1).sum()),
        "avg_gross": float(H.abs().sum(axis=1).replace(0, np.nan).mean()),
        "mean_mult": float(m[H.abs().sum(axis=1) > 0].mean()) if vol_target or corr_gate else 1.0,
        "min_mult": float(m[H.abs().sum(axis=1) > 0].min()) if vol_target or corr_gate else 1.0,
    }
    return equity, port_ret, meta


def blend_returns(rets_list, weights):
    """Combina rendimenti di piu' fattori (blend a livello di return series)."""
    out = pd.Series(0.0, index=rets_list[0].index)
    for r, w in zip(rets_list, weights):
        out = out + w * r
    return out


# ── challenge simulation ──────────────────────────────────────────────────────

def stats(eq, ret):
    sh = ret.mean() / ret.std() * np.sqrt(PPY) if ret.std() else 0.0
    dd = float((eq / eq.cummax() - 1).min())
    return float(eq.iloc[-1] - 1), float(sh), dd


def simulate_challenge(eq, ret, target_pct, dd_limit, daily_limit, safety=0.9):
    """Simula il passaggio di una challenge dati i rendimenti grezzi.

    Trova il sizing massimo k_max che rispetta i vincoli (DD static + daily loss),
    poi valuta se il target e' raggiungibile.
    Ritorna dict: k_max, scaled_return, scaled_dd, scaled_worst_day,
                  days_to_target, pass, fail_reason
    """
    total_ret, sharpe, maxdd = stats(eq, ret)

    # peggior giorno (rendimento daily sommato su 24h)
    daily_ret = ret.resample("24h").sum()
    worst_day = float(daily_ret.min())

    # sizing massimo: il vincolo piu' stringente vince
    maxdd_pos = abs(maxdd) if abs(maxdd) > 0 else 1e-9
    worst_pos = abs(worst_day) if abs(worst_day) > 0 else 1e-9
    k_dd = dd_limit / maxdd_pos
    k_daily = daily_limit / worst_pos
    k_max = min(k_dd, k_daily) * safety

    if k_max <= 0:
        return {"k_max": 0.0, "scaled_ret": 0.0, "scaled_dd": 0.0,
                "scaled_worst_day": 0.0, "days_to_target": -1,
                "pass": False, "fail_reason": "k_max<=0 (DD/giorno infinito)"}

    # riscala i rendimenti e ricalcola equity + metriche
    scaled_ret = ret * k_max
    scaled_eq = (1.0 + scaled_ret).cumprod()
    scaled_total = float(scaled_eq.iloc[-1] - 1)
    scaled_dd = float((scaled_eq / scaled_eq.cummax() - 1).min())
    scaled_worst_day = float((scaled_ret.resample("24h").sum()).min())

    # tempo al target: primo giorno in cui equity >= start * (1 + target)
    target_level = 1.0 + target_pct
    hit = scaled_eq[scaled_eq >= target_level]
    if len(hit):
        # delta in giorni dall'inizio (timedelta robusto, non dayofyear che wrappa a capodanno)
        days_to_target = int((hit.index[0] - scaled_eq.index[0]).total_seconds() / 86400)
    else:
        days_to_target = -1

    # calcolo annualizzato per confronto onesto
    n_days = len(scaled_ret) / 24.0
    ann_ret = scaled_total * (365.0 / n_days) if n_days > 0 else 0.0

    pass_ = scaled_total >= target_pct
    fail_reason = ""
    if not pass_:
        if days_to_target < 0:
            fail_reason = f"target {target_pct:.0%} non raggiunto in {n_days:.0f}g (ret {scaled_total:+.1%})"
        else:
            fail_reason = ""

    return {
        "k_max": k_max,
        "scaled_ret": scaled_total,
        "ann_ret": ann_ret,
        "scaled_dd": scaled_dd,
        "scaled_worst_day": scaled_worst_day,
        "days_to_target": days_to_target,
        "pass": pass_,
        "fail_reason": fail_reason,
    }


# ── definizione delle 15 strategie ────────────────────────────────────────────

def define_strategies():
    """Ogni strategia e' una dict con config. `factor` indica il pannello segnale,
    `weight` la funzione peso, + params (gross, vol_target, corr_gate, rebalance_h)."""
    S = []
    # ── AlphaZero (5): massimizza Sharpe, gross aggressivo, no de-risk ──
    S.append(dict(name="az-tsmom-highvol-5050", group="AlphaZero",
                  factors=[("tsmom_168", 0.5), ("highvol_72", 0.5)],
                  weight=sign_weights, rebalance_h=168, gross=1.5,
                  note="combo direzionale tsmom+highvol (NUOVO, non dollar-neutral)"))
    S.append(dict(name="az-liqimb-highvol-5050", group="AlphaZero",
                  factors=[("liqimb_7d", 0.5), ("highvol_72", 0.5)],
                  weight=terzile_weights, rebalance_h=24, gross=1.5,
                  note="combo liqimb+highvol (NUOVO)"))
    S.append(dict(name="az-trifactor-trend", group="AlphaZero",
                  factors=[("tsmom_168", 0.4), ("highvol_72", 0.3), ("liqimb_7d", 0.3)],
                  weight=None, rebalance_h=168, gross=1.5,
                  note="blend 3 fattori direzionali (no xsmom, NUOVO)"))
    S.append(dict(name="az-tsmom-multihorizon", group="AlphaZero",
                  factors=[("tsmom_96", 1/3), ("tsmom_168", 1/3), ("tsmom_336", 1/3)],
                  weight=sign_weights, rebalance_h=168, gross=1.5,
                  note="tsmom media 3 lookback, direzionale"))
    S.append(dict(name="az-highvol-lb168", group="AlphaZero",
                  factors=[("highvol_168", 1.0)],
                  weight=terzile_weights, rebalance_h=168, gross=2.0,
                  note="highvol su lookback 168h (vs 72h esistente)"))

    # ── Prop Turbo (5): 3% DD, vol-target obbligato ──
    S.append(dict(name="turbo-vt-xsmom", group="Turbo",
                  factors=[("xsmom_168", 1.0)],
                  weight=terzile_weights, rebalance_h=168, gross=1.0,
                  vol_target=0.15, gross_floor=0.3, gross_cap=1.0,
                  note="xsmom + vol-target overlay 15%"))
    S.append(dict(name="turbo-vt-liqimb", group="Turbo",
                  factors=[("liqimb_7d", 1.0)],
                  weight=terzile_weights, rebalance_h=24, gross=1.0,
                  vol_target=0.15, gross_floor=0.3, gross_cap=1.0,
                  note="liqimb + vol-target 15%"))
    S.append(dict(name="turbo-vt-tsmom-highvol", group="Turbo",
                  factors=[("tsmom_168", 0.5), ("highvol_72", 0.5)],
                  weight=sign_weights, rebalance_h=168, gross=1.0,
                  vol_target=0.15, gross_floor=0.3, gross_cap=1.0,
                  note="combo tsmom+highvol + vol-target 15%"))
    S.append(dict(name="turbo-corr-gate-xshv", group="Turbo",
                  factors=[("xsmom_168", 0.5), ("highvol_72", 0.5)],
                  weight=terzile_weights, rebalance_h=168, gross=1.0,
                  vol_target=0.15, gross_floor=0.3, gross_cap=1.0,
                  corr_gate=True, corr_threshold=0.8,
                  note="combo xshv + vol-target + correlation gate (NUOVO, Hedge #3)"))
    S.append(dict(name="turbo-quad-tailshield", group="Turbo",
                  factors=[("xsmom_168", 0.3), ("highvol_72", 0.25), ("liqimb_7d", 0.25), ("tsmom_168", 0.2)],
                  weight=None, rebalance_h=168, gross=1.0,
                  vol_target=0.12, gross_floor=0.2, gross_cap=1.0,
                  note="4-fattori + vol-target 12% + floor 0.2 (minimo rischio)"))

    # ── Prop Normale (5): 6% DD, moderato ──
    S.append(dict(name="normal-tsmom-highvol-6040", group="Normale",
                  factors=[("tsmom_168", 0.6), ("highvol_72", 0.4)],
                  weight=sign_weights, rebalance_h=168, gross=1.0,
                  note="combo tsmom+highvol 60/40"))
    S.append(dict(name="normal-liqimb-xsmom-5050", group="Normale",
                  factors=[("liqimb_7d", 0.5), ("xsmom_168", 0.5)],
                  weight=None, rebalance_h=168, gross=1.0,
                  note="combo liqimb+xsmom 50/50 (NUOVO)"))
    S.append(dict(name="normal-vt-light-xshv", group="Normale",
                  factors=[("xsmom_168", 0.5), ("highvol_72", 0.5)],
                  weight=terzile_weights, rebalance_h=168, gross=1.0,
                  vol_target=0.30, gross_floor=0.5, gross_cap=1.2,
                  note="combo xshv + vol-target leggero 30%"))
    S.append(dict(name="normal-trifactor", group="Normale",
                  factors=[("tsmom_168", 0.4), ("highvol_72", 0.3), ("liqimb_7d", 0.3)],
                  weight=None, rebalance_h=168, gross=1.0,
                  note="tsmom+highvol+liqimb 3-fattori"))
    S.append(dict(name="normal-highvol-lb168-reb48", group="Normale",
                  factors=[("highvol_168", 1.0)],
                  weight=terzile_weights, rebalance_h=48, gross=1.0,
                  note="highvol lb168 reb48"))

    return S


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12)
    a = ap.parse_args()

    syms = CRYPTO.split(",")
    px = grid_panel(syms, a.months)
    vol = grid_panel(syms, a.months, col="volume")
    fund = funding_panel(syms, a.months)
    liq_l = coinalyze_panel(syms, px.index, "liq_long")
    liq_s = coinalyze_panel(syms, px.index, "liq_short")
    oi = coinalyze_panel(syms, px.index, "oi")
    bt = PortfolioBacktest(px, fee=HL_TAKER_FEE, slippage=VALIDATION_SLIPPAGE)
    factors = build_factors(px, vol, liq_l, liq_s, oi)

    # baseline buy&hold
    beq = equal_weight_bh(px)
    br, bs, bdd = stats(beq, px.pct_change().fillna(0.0).mean(axis=1))

    strategies = define_strategies()

    print(f"basket {list(px.columns)}, {len(px)}h "
          f"({px.index.min():%Y-%m-%d} -> {px.index.max():%Y-%m-%d})")
    print(f"fee {HL_TAKER_FEE} + slip {VALIDATION_SLIPPAGE} | funding modellato | n_trials DSR={len(strategies)}")
    print(f"B&H equal-w baseline: ret {br:+.1%} Sharpe {bs:.2f} maxDD {bdd:+.1%}\n")

    # challenge configs
    CHALLENGES = {
        "Turbo":   dict(target_pct=0.09, dd_limit=0.03, daily_limit=0.03),
        "Normale": dict(target_pct=0.10, dd_limit=0.06, daily_limit=0.03),
    }

    results = []
    trial_srs = []
    for strat in strategies:
        # ── build per-factor return series, then blend ───────────────────
        factor_rets = []
        for fname, fw in strat["factors"]:
            sig_panel = factors[fname]
            wf = strat["weight"]
            # per le combo miste (weight=None) uso terzile per xsmom/highvol/liqimb,
            # sign per tsmom — decido in base al nome fattore
            if wf is None:
                wf = sign_weights if fname.startswith("tsmom") else terzile_weights
            eq_f, ret_f, meta_f = run_strategy(
                sig_panel, bt, fund, wf, strat["rebalance_h"],
                gross=strat["gross"],
                vol_target=strat.get("vol_target"),
                gross_floor=strat.get("gross_floor", 0.3),
                gross_cap=strat.get("gross_cap", 1.5),
                corr_gate=strat.get("corr_gate", False),
                corr_threshold=strat.get("corr_threshold", 0.8),
            )
            factor_rets.append((ret_f, fw))

        # blend a livello di return (combo di fattori)
        if len(factor_rets) == 1:
            ret = factor_rets[0][0]
        else:
            ret = blend_returns([r for r, _ in factor_rets], [w for _, w in factor_rets])
        eq = (1.0 + ret).cumprod()

        r, sh, dd = stats(eq, ret)
        calmar = abs(r / dd) if abs(dd) > 1e-9 else 0.0
        trial_srs.append(ret.mean() / ret.std() if ret.std() else 0.0)

        # simula entrambe le challenge
        sim_t = simulate_challenge(eq, ret, **CHALLENGES["Turbo"])
        sim_n = simulate_challenge(eq, ret, **CHALLENGES["Normale"])

        results.append({
            "name": strat["name"], "group": strat["group"], "note": strat["note"],
            "ret": r, "sharpe": sh, "maxdd": dd, "calmar": calmar,
            "turbo": sim_t, "normale": sim_n, "ret_series": ret,
        })

    # ── DSR (correzione multiple testing) ─────────────────────────────────
    n_trials = len(strategies)
    for res in results:
        d = deflated_sharpe(res["ret_series"], n_trials, trial_srs, periods_per_year=PPY)
        res["dsr"] = d["dsr"]

    # ── OUTPUT ────────────────────────────────────────────────────────────
    print("=" * 120)
    print("RISULTATI BACKTEST 15 STRATEGIE — metriche grezze (gross 1.0 equivalente)")
    print("=" * 120)
    print(f"{'#':<3} {'strategia':<28} {'gruppo':<8} {'ret':>8} {'sharpe':>7} {'maxDD':>8} {'Calmar':>7} {'DSR':>5}")
    print("-" * 120)
    for i, res in enumerate(results, 1):
        print(f"{i:<3} {res['name']:<28} {res['group']:<8} "
              f"{res['ret']:>+8.1%} {res['sharpe']:>7.2f} {res['maxdd']:>+8.1%} "
              f"{res['calmar']:>7.2f} {res['dsr']:>5.2f}")

    print("\n" + "=" * 120)
    print("SIMULAZIONE CHALLENGE TURBO (target 9% / DD 3% static / daily 3%)")
    print("=" * 120)
    print(f"{'strategia':<28} {'k_max':>6} {'ret@k':>8} {'ann@k':>8} {'DD@k':>7} {'worstD':>7} {'gg':>5} {'esito':<10}")
    print("-" * 120)
    for res in results:
        s = res["turbo"]
        esito = "PASS" if s["pass"] else "FAIL"
        gg = f"{s['days_to_target']}" if s["days_to_target"] > 0 else "-"
        print(f"{res['name']:<28} {s['k_max']:>6.2f} {s['scaled_ret']:>+8.1%} "
              f"{s['ann_ret']:>+8.1%} {s['scaled_dd']:>+7.1%} {s['scaled_worst_day']:>+7.1%} "
              f"{gg:>5} {esito:<10}")

    print("\n" + "=" * 120)
    print("SIMULAZIONE CHALLENGE NORMALE (target 10% / DD 6% static / daily 3%)")
    print("=" * 120)
    print(f"{'strategia':<28} {'k_max':>6} {'ret@k':>8} {'ann@k':>8} {'DD@k':>7} {'worstD':>7} {'gg':>5} {'esito':<10}")
    print("-" * 120)
    for res in results:
        s = res["normale"]
        esito = "PASS" if s["pass"] else "FAIL"
        gg = f"{s['days_to_target']}" if s["days_to_target"] > 0 else "-"
        print(f"{res['name']:<28} {s['k_max']:>6.2f} {s['scaled_ret']:>+8.1%} "
              f"{s['ann_ret']:>+8.1%} {s['scaled_dd']:>+7.1%} {s['scaled_worst_day']:>+7.1%} "
              f"{gg:>5} {esito:<10}")

    # ── riepilogo ─────────────────────────────────────────────────────────
    print("\n" + "=" * 120)
    print("RIEPILOGO")
    print("=" * 120)
    turbo_pass = [r for r in results if r["turbo"]["pass"]]
    norm_pass = [r for r in results if r["normale"]["pass"]]
    az_top = sorted([r for r in results if r["group"] == "AlphaZero"], key=lambda x: -x["sharpe"])
    print(f"Turbo: {len(turbo_pass)}/15 passano (3% DD)")
    print(f"Normale: {len(norm_pass)}/15 passano (6% DD)")
    print(f"AlphaZero top 3 per Sharpe: {', '.join(f'{r['name']} ({r['sharpe']:.2f})' for r in az_top[:3])}")
    if turbo_pass:
        best_t = min(turbo_pass, key=lambda r: r["turbo"]["days_to_target"] if r["turbo"]["days_to_target"] > 0 else 9999)
        print(f"Turbo piu' veloce: {best_t['name']} in {best_t['turbo']['days_to_target']}g")
    if norm_pass:
        best_n = min(norm_pass, key=lambda r: r["normale"]["days_to_target"] if r["normale"]["days_to_target"] > 0 else 9999)
        print(f"Normale piu' veloce: {best_n['name']} in {best_n['normale']['days_to_target']}g")


if __name__ == "__main__":
    main()
