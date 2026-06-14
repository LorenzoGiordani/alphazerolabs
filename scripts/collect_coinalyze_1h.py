"""Forward-collection liquidazioni/OI a 1h da Coinalyze → data/coinalyze_1h/<COIN>.parquet.

Coinalyze tiene solo ~1500-2000 punti intraday (a 1h ≈ 2.5 mesi), il vecchio è
cancellato ogni giorno. Girando periodicamente e APPENDENDO (dedup per ts) accumuliamo
storico 1h oltre la retention → tra settimane potremo testare `liq_imbalance` a
risoluzione fine (potenzialmente più forte del daily).

Dati NON rigenerabili oltre la finestra di retention → vanno versionati (data/coinalyze_1h/).
Riusa gli helper di fetch_coinalyze. Key: COINALYZE_API_KEY (env o .env).

Uso:  .venv/bin/python scripts/collect_coinalyze_1h.py --symbols BTC,ETH,SOL,XRP,SUI,NEAR,WLD,ZEC,CRV
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.fetch_coinalyze import api_key, perp_symbols, aggregate, get  # noqa: E402

OUT_DIR = ROOT / "data/coinalyze_1h"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--lookback-days", type=int, default=75, help="finestra da ripullire (≤ retention 1h)")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    s = requests.Session(); s.headers["api_key"] = api_key()
    markets = get(s, "future-markets", None)
    to = int(time.time()); frm = to - args.lookback_days * 86400

    for coin in args.symbols.split(","):
        coin = coin.strip()
        syms = perp_symbols(markets, coin)
        if not syms:
            print(f"  {coin}: nessun perp"); continue
        common = {"symbols": ",".join(syms), "interval": "1hour", "from": frm, "to": to}
        liq = aggregate(get(s, "liquidation-history", {**common, "convert_to_usd": "true"}),
                        {"liq_long": "l", "liq_short": "s"})
        oi = aggregate(get(s, "open-interest-history", {**common, "convert_to_usd": "true"}),
                       {"oi": "c"})
        if liq.empty:
            print(f"  {coin}: nessuna liquidazione 1h"); continue
        df = liq.merge(oi, on="ts", how="left") if not oi.empty else liq
        path = OUT_DIR / f"{coin}.parquet"
        if path.exists():
            df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
        df = df.drop_duplicates(subset=["ts"], keep="last").sort_values("ts")
        df.to_parquet(path, index=False)
        span = f"{df.ts.min():%Y-%m-%d}→{df.ts.max():%Y-%m-%d}"
        print(f"  {coin}: {len(df)} ore accumulate ({span}) → data/coinalyze_1h/{coin}.parquet")


if __name__ == "__main__":
    main()
