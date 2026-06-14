"""Scarica i metrics futures storici da Binance Vision (gratis) → data/metrics/<SYM>.parquet.

Binance pubblica dump giornalieri a 5-min con: open interest, ratio long/short dei
TOP TRADER (posizionamento smart-money), ratio long/short globale (crowding retail),
taker buy/sell ratio (flow). Dati che ci mancavano, gratis e con storico reale —
niente liquidazioni dirette, ma OI + posizionamento sono segnali leading equivalenti.

Solo crypto (perps USDT Binance); i nostri xyz_* (HIP-3) non ci sono.
Anti-lookahead: ogni riga è il valore al suo timestamp; i segnali fanno merge_asof
backward sulle candele.

Uso:  .venv/bin/python scripts/fetch_binance_metrics.py --symbols BTC,ETH,SOL,SUI,ZEC --months 6
"""

import argparse
import io
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data/metrics"
BASE = "https://data.binance.vision/data/futures/um/daily/metrics"


def fetch_day(sym_pair: str, d: date) -> pd.DataFrame | None:
    url = f"{BASE}/{sym_pair}/{sym_pair}-metrics-{d.isoformat()}.zip"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return None
        z = zipfile.ZipFile(io.BytesIO(r.content))
        with z.open(z.namelist()[0]) as f:
            return pd.read_csv(f)
    except Exception:
        return None


def fetch_symbol(sym: str, months: int) -> pd.DataFrame:
    pair = f"{sym}USDT"
    end = date.today()
    start = end - timedelta(days=months * 30 + 2)
    frames = []
    d = start
    while d <= end:
        df = fetch_day(pair, d)
        if df is not None and not df.empty:
            frames.append(df)
        d += timedelta(days=1)
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame({
        "ts": pd.to_datetime(raw["create_time"], utc=True),
        "oi": raw["sum_open_interest"].astype(float),
        "oi_value": raw["sum_open_interest_value"].astype(float),
        "toptrader_pos_ratio": raw["sum_toptrader_long_short_ratio"].astype(float),
        "global_account_ratio": raw["count_long_short_ratio"].astype(float),
        "taker_ratio": raw["sum_taker_long_short_vol_ratio"].astype(float),
    }).sort_values("ts")
    # risoluzione 1h (ultimo valore dell'ora) per allinearsi alle candele e restare compatti
    out = out.set_index("ts").resample("1h").last().dropna(how="all").reset_index()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True, help="solo crypto perps USDT, es. BTC,ETH,SOL")
    ap.add_argument("--months", type=int, default=6)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for sym in args.symbols.split(","):
        sym = sym.strip()
        df = fetch_symbol(sym, args.months)
        if df.empty:
            print(f"  {sym}: nessun dato metrics"); continue
        df.to_parquet(OUT_DIR / f"{sym}.parquet", index=False)
        print(f"  {sym}: {len(df)} ore "
              f"({df['ts'].min().date()}→{df['ts'].max().date()}) → data/metrics/{sym}.parquet")


if __name__ == "__main__":
    main()
