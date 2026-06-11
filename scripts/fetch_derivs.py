"""Dati derivati per segnali leading (Binance futures, gratis, no key).

- Funding rate: storico completo (8h) → data/funding/<sym>.parquet
- Taker flow: klines futures 1h con taker buy volume → data/flow/<sym>.parquet

Nota: open interest storico su Binance è limitato a 30 giorni → niente segnale
OI nel backtest lungo; si aggiunge in paper trading (dati live).
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

FAPI = "https://fapi.binance.com"
MONTHS = 12
SYMBOLS = ["BTC", "ETH", "SOL", "XRP", "SUI", "NEAR", "WLD", "ZEC", "CRV"]  # core con storico Binance


def paged(url: str, params: dict, ts_key: str) -> list:
    rows, start = [], params.pop("startTime")
    while True:
        r = requests.get(url, params={**params, "startTime": start, "limit": 1000}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows += batch
        last = batch[-1][ts_key] if isinstance(batch[-1], dict) else batch[-1][0]
        start = last + 1
        if len(batch) < 1000:
            break
        time.sleep(0.15)
    return rows


def main() -> None:
    Path("data/funding").mkdir(parents=True, exist_ok=True)
    Path("data/flow").mkdir(parents=True, exist_ok=True)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=30 * MONTHS)).timestamp() * 1000)

    for sym in SYMBOLS:
        pair = f"{sym}USDT"
        try:
            fr = paged(f"{FAPI}/fapi/v1/fundingRate", {"symbol": pair, "startTime": start_ms}, "fundingTime")
            fdf = pd.DataFrame({
                "ts": pd.to_datetime([r["fundingTime"] for r in fr], unit="ms", utc=True),
                "rate": [float(r["fundingRate"]) for r in fr]})
            fdf.to_parquet(f"data/funding/{sym}.parquet", index=False)

            kl = paged(f"{FAPI}/fapi/v1/klines", {"symbol": pair, "interval": "1h", "startTime": start_ms}, "0")
            kdf = pd.DataFrame({
                "ts": pd.to_datetime([k[0] for k in kl], unit="ms", utc=True),
                "volume": [float(k[5]) for k in kl],
                "taker_buy": [float(k[9]) for k in kl]})
            kdf.to_parquet(f"data/flow/{sym}.parquet", index=False)
            print(f"{sym:<6} funding {len(fdf):>5} | flow {len(kdf):>5}")
        except Exception as e:
            print(f"{sym:<6} FALLITO: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
