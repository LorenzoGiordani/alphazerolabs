"""Precompute rank cross-sectional → cache parquet per simbolo (anti-lookahead).

A ogni ora calcola, per ogni asset del basket, il PERCENTILE del suo ritorno
trailing (`lookback_h`) rispetto agli altri asset del basket → rank_pct in 0..100.
Il segnale signals.xsection_momentum legge questa cache (niente cross-asset a
runtime nel loop per-simbolo). Anti-lookahead: il rank a t usa solo close ≤ t.

Pattern identico a precompute_kronos/hmm: legge data/candles/<sym>.parquet, scrive
data/xsection/<sym>.parquet (ts, rank_pct). LLM-free e leggero → ok in cron.

Uso: uv run scripts/precompute_xsection.py --symbols BTC,ETH,SOL,... [--lookback-h 168] [--months 6]
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data/xsection"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True, help="basket, es. BTC,ETH,SOL")
    ap.add_argument("--lookback-h", type=int, default=168, help="finestra del ritorno trailing")
    ap.add_argument("--months", type=int, default=12)
    args = ap.parse_args()

    syms = [s.strip() for s in args.symbols.split(",")]
    cols = {}
    for s in syms:
        p = ROOT / f"data/candles/{s}.parquet"
        if p.exists():
            c = pd.read_parquet(p).tail(args.months * 30 * 24)
            cols[s] = c.set_index("ts")["close"]
    if len(cols) < 3:
        print(f"basket troppo piccolo ({len(cols)} asset con candele): serve >=3")
        return
    panel = pd.DataFrame(cols).sort_index()
    panel = panel[~panel.index.duplicated()]

    ret = panel.pct_change(args.lookback_h)
    rank_pct = ret.rank(axis=1, pct=True) * 100.0   # rank cross-sectional per timestamp

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for s in cols:
        out = pd.DataFrame({"ts": panel.index, "rank_pct": rank_pct[s].to_numpy()}).dropna()
        if out.empty:
            print(f"  {s}: nessun rank prodotto"); continue
        out.to_parquet(OUT_DIR / f"{s}.parquet", index=False)
        print(f"  {s}: {len(out)} rank → data/xsection/{s}.parquet "
              f"(ultimo {out.rank_pct.iloc[-1]:.0f}p)")


if __name__ == "__main__":
    main()
