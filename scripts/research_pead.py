"""Edge study PEAD/SUE sull'universo stock HIP-3 — PRIMA di ogni registry (regola #4).

Tesi (Bernard & Thomas 1989, replicata per 35 anni): dopo una sorpresa utili
positiva il titolo continua a salire per settimane (drift post-annuncio), e
viceversa. SUE time-series = (EPS_q − EPS_{q−4}) / std degli ultimi 8 scarti
stagionali — nessun consensus analisti, solo EDGAR (gratis, PIT via `filed`).

Falsificata se: IC eventi→fwd return non batte il random control (permutazione
delle SUE fra gli eventi, alpha_t < 3.5) o lo spread top−bottom tercile è ~0.

Protocollo anti-lookahead: entry alla CHIUSURA del primo giorno di borsa DOPO
il filed date; fwd return market-adjusted (− SPY stessa finestra) per togliere
il beta di mercato dagli eventi.

Uso: uv run scripts/research_pead.py [--years 8] [--fwd 5,20,60]
Output: verdetto per orizzonte + paper/pead_study.json
"""
import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EDGAR = ROOT / "data" / "edgar"
MIN_HIST = 8          # scarti stagionali per lo std della SUE
N_SHUFFLES = 200
ALPHA_T = 3.5


def load_prices(tickers: list[str], years: int) -> pd.DataFrame:
    """Close daily auto-adjusted da yfinance, cache locale."""
    cache = EDGAR / "px_daily.parquet"
    if cache.exists():
        px = pd.read_parquet(cache)
        if set(tickers + ["SPY"]).issubset(px.columns):
            return px
    import yfinance as yf
    px = yf.download(tickers + ["SPY"], period=f"{years}y", interval="1d",
                     auto_adjust=True, progress=False)["Close"]
    px.to_parquet(cache)
    return px


def sue_events(tickers: list[str]) -> pd.DataFrame:
    """Un evento per trimestre: SUE + filed date."""
    rows = []
    for t in tickers:
        p = EDGAR / f"eps_{t}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p).sort_values("end").reset_index(drop=True)
        df["seasonal_diff"] = df["val"] - df["val"].shift(4)
        for i in range(MIN_HIST + 4, len(df)):
            hist = df["seasonal_diff"].iloc[i - MIN_HIST:i].dropna()
            d = df["seasonal_diff"].iloc[i]
            if len(hist) < MIN_HIST - 2 or pd.isna(d) or hist.std() == 0:
                continue
            rows.append({"ticker": t, "end": df["end"].iloc[i],
                         "filed": df["filed"].iloc[i],
                         "sue": float(d / hist.std())})
    return pd.DataFrame(rows)


def fwd_return(px: pd.Series, spy: pd.Series, filed: pd.Timestamp, days: int):
    """Entry = close del primo giorno di borsa DOPO filed; ritorno market-adj."""
    after = px.index[px.index > filed]
    if len(after) < days + 1:
        return None
    t0, t1 = after[0], after[min(days, len(after) - 1)]
    if pd.isna(px.get(t0)) or pd.isna(px.get(t1)):
        return None
    r = px[t1] / px[t0] - 1
    rm = spy[t1] / spy[t0] - 1 if t0 in spy.index and t1 in spy.index else 0.0
    return float(r - rm)


def study(ev: pd.DataFrame, px: pd.DataFrame, fwd_days: int, seed: int = 0) -> dict:
    ev = ev.copy()
    spy = px["SPY"]
    ev["fwd"] = [fwd_return(px[e.ticker], spy, e.filed, fwd_days)
                 for e in ev.itertuples()]
    ev = ev.dropna(subset=["fwd"])
    n = len(ev)
    ic = float(ev["sue"].rank().corr(ev["fwd"].rank()))
    t_ic = ic * np.sqrt(n - 2) / np.sqrt(1 - ic**2) if abs(ic) < 1 else 0.0
    ter = ev["sue"].quantile([1 / 3, 2 / 3])
    top = ev[ev.sue >= ter.iloc[1]]["fwd"].mean()
    bot = ev[ev.sue <= ter.iloc[0]]["fwd"].mean()
    # random control: permuta le SUE fra gli eventi (stesso envelope, zero info)
    rng = np.random.default_rng(seed)
    rand_ics = []
    fr = ev["fwd"].rank().to_numpy()
    sr = ev["sue"].rank().to_numpy()
    for _ in range(N_SHUFFLES):
        rand_ics.append(float(np.corrcoef(rng.permutation(sr), fr)[0, 1]))
    rstd = float(np.std(rand_ics, ddof=1))
    alpha_t = (ic - float(np.mean(rand_ics))) / rstd if rstd > 0 else 0.0
    cat = ("confirmed_alive" if alpha_t >= ALPHA_T
           else "reversed" if alpha_t <= -ALPHA_T else "noise")
    return {"fwd_days": fwd_days, "n_events": n, "ic": round(ic, 3),
            "t_ic": round(float(t_ic), 1), "spread_top_bot": round(float(top - bot), 4),
            "alpha_t": round(float(alpha_t), 2), "category": cat}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=8)
    ap.add_argument("--fwd", default="5,20,60")
    a = ap.parse_args()
    warnings.filterwarnings("ignore")

    tickers = sorted(p.stem[4:] for p in EDGAR.glob("eps_*.parquet"))
    ev = sue_events(tickers)
    px = load_prices(tickers, a.years)
    ev = ev[ev.filed >= px.index.min()]
    print(f"eventi SUE: {len(ev)} su {ev.ticker.nunique()} ticker "
          f"({ev.filed.min():%Y-%m} → {ev.filed.max():%Y-%m})")

    results = [study(ev, px, int(d)) for d in a.fwd.split(",")]
    for r in results:
        print(f"  fwd {r['fwd_days']:>3}g: IC {r['ic']:+.3f} (t {r['t_ic']:+.1f}, "
              f"n {r['n_events']})  spread T−B {r['spread_top_bot']:+.2%}  "
              f"alpha_t {r['alpha_t']:+.1f} → {r['category']}")

    # sotto-periodo recente (regime attuale): ultimi 3 anni
    recent = ev[ev.filed >= ev.filed.max() - pd.Timedelta(days=3 * 365)]
    r3 = [study(recent, px, int(d), seed=1) for d in a.fwd.split(",")]
    print("ultimi 3 anni:")
    for r in r3:
        print(f"  fwd {r['fwd_days']:>3}g: IC {r['ic']:+.3f} (t {r['t_ic']:+.1f}, "
              f"n {r['n_events']})  spread {r['spread_top_bot']:+.2%}  "
              f"alpha_t {r['alpha_t']:+.1f} → {r['category']}")

    out = {"asof": datetime.now(timezone.utc).isoformat(),
           "universe": tickers, "protocol": {
               "sue": "seasonal-diff / std 8 scarti (Bernard-Thomas)",
               "entry": "close primo giorno dopo filed", "adj": "minus SPY",
               "alpha_t_threshold": ALPHA_T, "n_shuffles": N_SHUFFLES},
           "full_sample": results, "last_3y": r3}
    (ROOT / "paper/pead_study.json").write_text(json.dumps(out, indent=1))
    print("→ paper/pead_study.json")


if __name__ == "__main__":
    main()
