"""Valida l'espansione cross-asset di xsmom: crypto + commodities.

PROBLEMA: il basket crypto e' correlato 0.63 (tutto si muove insieme). Allargare a
commodities diversificherebbe il book MA c'e' un ostacolo: volatilita' molto
diverse (GOLD 7% vs NATGAS 23% vs SOL 14% annui). Rankare per ritorno GREZZO fa
diventare il book 'long alta-vol / short bassa-vol' sistematicamente = scommessa
di vol, non momentum relativo.

CURE testate (Asness-Moskowitz-Pedersen 2013, 'Value and Momentum Everywhere'):
  [A] RAW cross-asset          ret grezzo, ranking distorto (controllo negativo)
  [B] VOL-NORMALIZED cross     ret / rolling_vol → z-score, comparabile cross-asset
  [C] crypto-only (baseline)   per confronto (IC +0.089 t+21 noto)

Metrica: IC cross-section (rank corr) + spread top-bottom, a 168h fwd, 12m.
Se [B] >= [C], l'espansione ha senso e si costruisce la strategia portfolio.

Uso: uv run scripts/research_crossasset.py [--months 12]
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CRYPTO = "BTC,ETH,SOL,XRP,SUI,NEAR,WLD,ZEC,CRV"
COMMODITIES = "xyz_GOLD,xyz_SILVER,xyz_CL,xyz_BRENTOIL,xyz_NATGAS"


def panel(symbols, months):
    """Panel close su griglia oraria comune (reindex+ffill per session-based).
    Usa BTC come griglia di riferimento (unica veramente 24/7)."""
    btc = pd.read_parquet(ROOT / "data/candles/BTC.parquet").tail(months * 30 * 24)
    grid = pd.to_datetime(btc.ts, utc=True)
    cols = {}
    for s in symbols:
        p = ROOT / f"data/candles/{s}.parquet"
        if not p.exists():
            continue
        c = pd.read_parquet(p).copy()
        c["ts"] = pd.to_datetime(c.ts, utc=True)
        c = c.drop_duplicates("ts").set_index("ts")["close"]
        # reindex sulla griglia oraria continua, ffill (session gap = ultimo prezzo)
        cols[s] = c.reindex(grid, method="ffill")
    df = pd.DataFrame(cols).sort_index()
    return df[~df.index.duplicated()]


def row_ic(signal_panel, fwd_panel, min_assets=5):
    """IC cross-section per timestamp (rank corr), media + t-stat."""
    rs = signal_panel.rank(axis=1)
    rf = fwd_panel.rank(axis=1)
    valid = signal_panel.notna().sum(axis=1) >= min_assets
    rs, rf = rs[valid], rf[valid]
    rs = rs.sub(rs.mean(axis=1), axis=0)
    rf = rf.sub(rf.mean(axis=1), axis=0)
    num = (rs * rf).sum(axis=1)
    den = np.sqrt((rs ** 2).sum(axis=1) * (rf ** 2).sum(axis=1)).replace(0, np.nan)
    ic = (num / den).dropna()
    if len(ic) < 5 or ic.std() == 0:
        return np.nan, 0, 0.0
    t = ic.mean() / ic.std() * np.sqrt(len(ic))
    return float(ic.mean()), len(ic), float(t)


def spread_top_bottom(signal, fwd, min_assets=6):
    """Ritorno medio long-top-terzile − short-bottom-terzile, campionato ogni 168h."""
    out = []
    for t in signal.dropna(how="all").index[::168]:
        s, f = signal.loc[t], fwd.loc[t]
        ok = s.notna() & f.notna()
        if ok.sum() < min_assets:
            continue
        s, f = s[ok], f[ok]
        med = s.median()
        hi = f[s >= med].mean()
        lo = f[s < med].mean()
        out.append(hi - lo)
    return float(np.nanmean(out)) if out else float("nan")


def vol_normalize(panel_close, lookback_h=168):
    """Ritorno trailing normalizzato per volatilita' (z-score cross-asset).
    ret_trailing / rolling_std(ret_orario). Rende comparabili asset con vol diversa."""
    rets = panel_close.pct_change()
    vol = rets.rolling(lookback_h, min_periods=lookback_h // 2).std()
    trailing = panel_close.pct_change(lookback_h)
    return (trailing / vol.replace(0, np.nan)).fillna(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12)
    a = ap.parse_args()
    crypto = CRYPTO.split(",")
    comm = COMMODITIES.split(",")
    all_assets = crypto + comm

    px_all = panel(all_assets, a.months)
    px_crypto = px_all[crypto]
    px_comm = px_all[comm]
    print(f"basket: {len(crypto)} crypto + {len(comm)} commodities = {len(all_assets)} asset, "
          f"{len(px_all)} ore ({px_all.index.min():%Y-%m-%d} → {px_all.index.max():%Y-%m-%d})\n")

    hz = 168
    fwd_all = px_all.pct_change(hz).shift(-hz)
    fwd_crypto = px_crypto.pct_change(hz).shift(-hz)
    raw_all = px_all.pct_change(hz)
    raw_crypto = px_crypto.pct_change(hz)
    volnorm_all = vol_normalize(px_all, hz)

    print(f"{'config':<38} {'IC':>8} {'t':>6} {'spread TB':>10}  note")
    print("-" * 80)
    # baseline crypto-only
    ic, n, t = row_ic(raw_crypto, fwd_crypto)
    sp = spread_top_bottom(raw_crypto, fwd_crypto)
    print(f"{'[C] crypto-only RAW (baseline)':<38} {ic:>+8.4f} {t:>+6.1f} {sp:>+10.4f}  IC noto +0.089")

    # cross-asset raw (aspettativa: degradato/distorto)
    ic, n, t = row_ic(raw_all, fwd_all)
    sp = spread_top_bottom(raw_all, fwd_all)
    print(f"{'[A] cross-asset RAW (controllo negativo)':<38} {ic:>+8.4f} {t:>+6.1f} {sp:>+10.4f}  distorto da vol")

    # cross-asset vol-normalized (la mia ipotesi)
    ic, n, t = row_ic(volnorm_all, fwd_all)
    sp = spread_top_bottom(volnorm_all, fwd_all)
    verdict = "REGGE → costruisci" if t > 2 and ic > 0.05 else ("debole" if t > 1 else "falsificato")
    print(f"{'[B] cross-asset VOL-NORMALIZED':<38} {ic:>+8.4f} {t:>+6.1f} {sp:>+10.4f}  {verdict}")

    # breakdown per sottobasket (diagnostica: commodities da sole hanno edge?)
    raw_comm = px_comm.pct_change(hz)
    fwd_comm = px_comm.pct_change(hz).shift(-hz)
    ic, n, t = row_ic(raw_comm, fwd_comm, min_assets=4)
    print(f"{'    commodities-only RAW (5 asset)':<38} {ic:>+8.4f} {t:>+6.1f} {'—':>10}  sottobasket separato")

    print("\nVerdetto: se [B] >= [C] (IC e t), l'espansione cross-asset vol-normalizzata")
    print("ha senso. Se [B] < [C], le commodities non aggiungono edge relativo (meglio crypto-only).")


if __name__ == "__main__":
    main()
