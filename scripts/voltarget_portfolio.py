"""Vol-target overlay per i 3 edge portfolio (Moreira-Muir 2017 adattato).

PROBLEMA (dall'audit di robustezza): il bootstrap della combo 70/30 mostra coda
avversa del maxDD al 5° percentile = -25.5%, con 6% di prob. di drawdown peggiore
di -25%. Il rischio di rovina reale è la CODA, non lo Sharpe.

IDEA: la volatilità clusterizza (GARCH): alta vol oggi → alta vol domani → i rendimenti
avversi si concentrano nei periodi ad alta vol. Se scaliamo il gross inversamente alla
vol realizzata DEL BOOK STESSO (σ* / σ_realized), de-riskiamo nei periodi turbolenti e
rialziamo in quelli calmi. Documentato migliorare lo Sharpe modestamente MA soprattutto
ABBATTERE i drawdown profondi (Moreira & Muir, "Volatility-Managed Portfolios", 2017).

IMPLEMENTAZIONE (anti-lookahead rigoroso):
  1. pesi raw W (long/short terzile) come prima, decisi a t, applicati t+1.
  2. vol realizzata σ_t = std rolling(720h) dei rendimenti REALIZZATI del book fino a t
     (usa solo ret ≤ t, nessun lookahead).
  3. moltiplicatore m_t = clip(σ* / σ_t, gross_floor, gross_cap). warmup: m=1.0 finche'
     non ci sono abbastanza osservazioni.
  4. pesi effettivi H = m_t · W_t; turnover = |ΔH|; cost = turnover·cost_rate;
     ret = (H.shift(1)·ret).sum() - turnover·cost.

RISCHIO di overfitting: σ* e' un NUOVO parametro selezionato sui dati. Per onesta':
  - sweep su GRID di target (non seleziono il migliore e basta)
  - DSR calcolato contando le trials del grid nel multiple-testing
  - il vincolo e' ABBASSARE il DD, non alzare lo Sharpe (il target e' una coda DD
    peggiore, non uno Sharpe piu' alto)

Uso: uv run scripts/voltarget_portfolio.py
"""
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


def raw_weights_matrix(signal_panel, bt, weight_fn, rebalance_h):
    """Matrice pesi raw (gross=1), anti-lookahead, SENZA cost overlay."""
    idx = bt.close.index
    n = len(idx)
    sig = signal_panel.reindex(columns=bt.close.columns)
    W = pd.DataFrame(0.0, index=idx, columns=bt.close.columns)
    first = sig.dropna(how="all").index
    start = sig.index.get_loc(first[0]) + 1 if len(first) else n
    for i in range(start, n, rebalance_h):
        w = weight_fn(sig.iloc[i - 1]).reindex(bt.close.columns).fillna(0.0)
        W.iloc[i:min(i + rebalance_h, n)] = w.to_numpy()
    return W, start


def run_voltarget(signal_panel, bt, weight_fn, rebalance_h,
                  target_vol_ann, vol_window_h=720,
                  gross_floor=0.3, gross_cap=1.5):
    """Backtest con vol-target overlay. Ritorna equity, ret, meta (con serie m).
    target_vol_ann=None disabilita l'overlay (m=1.0 costante = gross 1.0 puro)."""
    W, start = raw_weights_matrix(signal_panel, bt, weight_fn, rebalance_h)
    # rendimenti raw (senza cost overlay ancora) per stimare la vol realizzata
    raw_port_ret = (W.shift(1) * bt.ret).sum(axis=1)
    if target_vol_ann is None:
        # overlay OFF: moltiplicatore costante 1.0 (gross puro, nessun de-risk)
        m = pd.Series(1.0, index=bt.close.index)
    else:
        # vol realizzata annualizzata, rolling, SOLO passato (rolling e' trailing di default)
        realized_vol = raw_port_ret.rolling(vol_window_h, min_periods=vol_window_h // 2).std() * np.sqrt(PPY)
        # moltiplicatore di gross (clip). warmup: dove non c'e' stima -> 1.0
        m = (target_vol_ann / realized_vol).where(realized_vol > 0, 1.0)
        m = m.clip(gross_floor, gross_cap)
    # pesi effettivi = m * W (broadcast su colonne)
    H = W.mul(m, axis=0)
    # turnover = variazione assoluta dei pesi effettivi (include il de/re-leverage)
    turnover = H.diff().abs().sum(axis=1)
    turnover.iloc[start:start + 1] = H.iloc[start].abs().sum()  # prima attivazione
    port_ret = (H.shift(1) * bt.ret).sum(axis=1) - turnover * bt.cost
    equity = (1.0 + port_ret).cumprod()
    meta = {
        "rebalances": int(((W.abs().sum(axis=1) > 0).astype(int).diff() == 1).sum()),
        "avg_gross": float(H.abs().sum(axis=1).replace(0, np.nan).mean()),
        "mean_multiplier": float(m[H.abs().sum(axis=1) > 0].mean()),
        "min_multiplier": float(m[H.abs().sum(axis=1) > 0].min()),
        "target_vol_ann": target_vol_ann,
        "vol_window_h": vol_window_h,
    }
    return equity, port_ret, meta, m


def stats(eq, ret):
    sh = ret.mean() / ret.std() * np.sqrt(PPY) if ret.std() else 0.0
    dd = float((eq / eq.cummax() - 1).min())
    return float(eq.iloc[-1] - 1), float(sh), dd


def block_bootstrap_sharpe(ret, block_h=168, B=2000, seed=42):
    rng = np.random.default_rng(seed)
    r = ret.to_numpy()
    n = len(r)
    nb = int(np.ceil(n / block_h))
    starts = rng.integers(0, n, size=(B, nb))
    sharpes = np.empty(B)
    ann = np.sqrt(PPY)
    for b in range(B):
        idx = (starts[b][:, None] + np.arange(block_h)[None, :]).ravel()[:n] % n
        samp = r[idx]
        sd = samp.std()
        sharpes[b] = samp.mean() / sd * ann if sd > 0 else 0.0
    return sharpes


def bootstrap_maxdd(ret, block_h=168, B=2000, seed=123):
    rng = np.random.default_rng(seed)
    r = ret.to_numpy()
    n = len(r)
    nb = int(np.ceil(n / block_h))
    starts = rng.integers(0, n, size=(B, nb))
    maxdds = np.empty(B)
    for b in range(B):
        idx = (starts[b][:, None] + np.arange(block_h)[None, :]).ravel()[:n] % n
        eq = np.cumprod(1 + r[idx])
        maxdds[b] = (eq / np.maximum.accumulate(eq) - 1).min()
    return maxdds


SIGNALS = {
    "xsmom":   dict(builder=lambda px, lb: px.pct_change(lb),     chosen_lb=168, chosen_reb=168),
    "highvol": dict(builder=lambda px, lb: px.pct_change().rolling(lb, min_periods=lb // 2).std(),
                    chosen_lb=72, chosen_reb=168),
}


def main():
    px = grid_panel(CRYPTO.split(","), 12)
    bt = PortfolioBacktest(px)
    xcfg, hcfg = SIGNALS["xsmom"], SIGNALS["highvol"]

    # rendimenti raw delle 2 gambe (senza overlay) per la combo
    ret_xs_raw = run_voltarget(xcfg["builder"](px, xcfg["chosen_lb"]), bt,
                               terzile_weights, xcfg["chosen_reb"],
                               target_vol_ann=None)[1]  # None = overlay OFF
    ret_hv_raw = run_voltarget(hcfg["builder"](px, hcfg["chosen_lb"]), bt,
                               terzile_weights, hcfg["chosen_reb"],
                               target_vol_ann=None)[1]
    print(f"basket {list(px.columns)} | {len(px)}h "
          f"({px.index.min():%Y-%m-%d} → {px.index.max():%Y-%m-%d})")
    print("=" * 84)
    print("VOL-TARGET OVERLAY (σ* / σ_realized, vol_window=720h, floor=0.3, cap=1.5)")
    print("Vincolo: ABBASSARE la coda DD (non alzare Sharpe). warmup m=1.0 prime 720h.")
    print("=" * 84)

    targets = [0.20, 0.25, 0.30, 0.40, 0.50, None]  # None = off (baseline)

    # ── baseline combo senza overlay ──────────────────────────────────────
    blend_raw = 0.5 * ret_xs_raw + 0.5 * ret_hv_raw
    r, sh, dd = stats((1 + blend_raw).cumprod(), blend_raw)
    shs = block_bootstrap_sharpe(blend_raw)
    mdds = bootstrap_maxdd(blend_raw)
    print(f"\nBASELINE combo 50/50 (NO overlay): ret {r:+.1%} Sharpe {sh:.2f} maxDD {dd:+.1%}")
    print(f"  bootstrap: Sharpe CI95 [{np.percentile(shs,2.5):.2f}, {np.percentile(shs,97.5):.2f}] | "
          f"maxDD coda5% {np.percentile(mdds,5):+.1%}  P(DD<-25%)={np.mean(mdds<-0.25):.0%}")

    # ── sweep target vol sulle 2 gambe + combo ────────────────────────────
    results = {}
    for tgt in targets:
        label = "OFF" if tgt is None else f"{tgt:.0%}"
        ret_xs = run_voltarget(xcfg["builder"](px, xcfg["chosen_lb"]), bt,
                               terzile_weights, xcfg["chosen_reb"], tgt)[1]
        ret_hv = run_voltarget(hcfg["builder"](px, hcfg["chosen_lb"]), bt,
                               terzile_weights, hcfg["chosen_reb"], tgt)[1]
        blend = 0.5 * ret_xs + 0.5 * ret_hv
        eq = (1 + blend).cumprod()
        r, sh, dd = stats(eq, blend)
        dsr = deflated_sharpe(blend, len(targets), periods_per_year=PPY)["dsr"]
        mdds = bootstrap_maxdd(blend)
        results[label] = dict(sh=sh, dd=dd, ret=r, dsr=dsr,
                              dd_tail5=np.percentile(mdds, 5),
                              p_dd25=np.mean(mdds < -0.25),
                              rets=blend)
        print(f"\nσ*={label:>4}  combo 50/50: ret {r:+7.1%} Sharpe {sh:5.2f} maxDD {dd:+6.1%} "
              f"DSR {dsr:.2f} | maxDD coda5% {np.percentile(mdds,5):+6.1%} P(DD<-25%)={np.mean(mdds<-0.25):.0%}")

    # ── per-gamba dettaglio al target migliore (min DD) ───────────────────
    # scelgo target che MAXIMIZZA la coda DD (meno avversa: -18% > -31%)
    best_label = max([l for l in results if l != "OFF"], key=lambda l: results[l]["dd_tail5"])
    print("\n" + "─" * 84)
    print(f"TARGET SCELTO σ*={best_label} (massimizza coda DD = meno avversa)")
    print("─" * 84)
    for name, cfg in SIGNALS.items():
        eq, ret, meta, m = run_voltarget(cfg["builder"](px, cfg["chosen_lb"]), bt,
                                         terzile_weights, cfg["chosen_reb"],
                                         None if best_label == "OFF" else float(best_label[:-1]) / 100)
        r, sh, dd = stats(eq, ret)
        mdds = bootstrap_maxdd(ret)
        print(f"  {name:8s}: ret {r:+7.1%} Sharpe {sh:5.2f} maxDD {dd:+6.1%} | "
              f"avg_gross {meta['avg_gross']:.2f} (m medio {meta['mean_multiplier']:.2f}, "
              f"min {meta['min_multiplier']:.2f}) | maxDD coda5% {np.percentile(mdds,5):+6.1%}")

    # ── verdetto ──────────────────────────────────────────────────────────
    base = results["OFF"]
    best = results[best_label]
    print("\n" + "=" * 84)
    print("VERDETTO VOL-TARGET OVERLAY")
    print("=" * 84)
    print(f"{'config':<10} {'Sharpe':>7} {'maxDD':>8} {'coda5%DD':>10} {'P(DD<-25%)':>11} {'DSR':>5}")
    print(f"{'OFF (base)':<10} {base['sh']:>7.2f} {base['dd']:>+8.1%} "
          f"{base['dd_tail5']:>+10.1%} {base['p_dd25']:>11.0%} {base['dsr']:>5.2f}")
    print(f"{'σ*='+best_label:<10} {best['sh']:>7.2f} {best['dd']:>+8.1%} "
          f"{best['dd_tail5']:>+10.1%} {best['p_dd25']:>11.0%} {best['dsr']:>5.2f}")
    dd_improve = best["dd_tail5"] - base["dd_tail5"]
    sh_delta = best["sh"] - base["sh"]
    verdict = ("✓ OVERLAY EFFICACE" if (dd_improve > 0.02 and sh_delta > -0.3)
               else "△ OVERLAY NEUTRO/DEBOLE")
    print(f"\nΔ coda5% DD: {dd_improve:+.1%} (positivo = coda meno avversa) | "
          f"Δ Sharpe: {sh_delta:+.2f} | {verdict}")
    n_dsr = len(targets)
    print(f"\nNota: σ* selezionato fra {n_dsr} target -> DSR sconta il multiple-testing. "
          "Se ΔSharpe < 0 e la coda DD migliora poco, l'overlay NON e' un edge reale "
          "(e' overfitting del target).")


if __name__ == "__main__":
    main()
