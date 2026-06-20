"""Step 1 — candele storiche 1h per il backtest (12 mesi dove possibile).

Fonti per priorità:
- crypto: Binance (storico lungo, gratis, no key)
- asset solo-HL (es. HYPE): API HL candleSnapshot (lookback ~5000 candele)
- stock/commodity perps xyz: sottostante via yfinance (i mercati HIP-3 sono giovani)

Output: data/candles/<symbol>.parquet (colonne: ts, open, high, low, close, volume)
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path("data/candles")
MONTHS = 12
N_CORE = 12   # top crypto perps per volume
N_XYZ = 8     # top stock/commodity perps per volume

BINANCE_URL = "https://api.binance.com/api/v3/klines"
HL_INFO_URL = "https://api.hyperliquid.xyz/info"

# xyz symbol → ticker yfinance del sottostante
XYZ_TO_YF = {
    "SP500": "^GSPC", "XYZ100": "^NDX", "GOLD": "GC=F", "SILVER": "SI=F",
    "CL": "CL=F", "BRENTOIL": "BZ=F", "NATGAS": "NG=F", "COPPER": "HG=F",
    "SKHX": "000660.KS",
}


def from_binance(coin: str, start: datetime) -> pd.DataFrame | None:
    rows, start_ms = [], int(start.timestamp() * 1000)
    while True:
        r = requests.get(BINANCE_URL, params={
            "symbol": f"{coin}USDT", "interval": "1h",
            "startTime": start_ms, "limit": 1000}, timeout=30)
        if r.status_code != 200:
            return None
        batch = r.json()
        if not batch:
            break
        rows += batch
        start_ms = batch[-1][0] + 3_600_000
        if len(batch) < 1000:
            break
        time.sleep(0.1)
    if not rows:
        return None
    df = pd.DataFrame(rows).iloc[:, :6]
    df.columns = ["ts", "open", "high", "low", "close", "volume"]
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.astype({c: float for c in ["open", "high", "low", "close", "volume"]})


def from_hyperliquid(coin: str, start: datetime) -> pd.DataFrame | None:
    r = requests.post(HL_INFO_URL, json={"type": "candleSnapshot", "req": {
        "coin": coin, "interval": "1h",
        "startTime": int(start.timestamp() * 1000),
        "endTime": int(datetime.now(timezone.utc).timestamp() * 1000)}}, timeout=30)
    if r.status_code != 200 or not r.json():
        return None
    df = pd.DataFrame(r.json())
    out = pd.DataFrame({
        "ts": pd.to_datetime(df["t"], unit="ms", utc=True),
        "open": df["o"].astype(float), "high": df["h"].astype(float),
        "low": df["l"].astype(float), "close": df["c"].astype(float),
        "volume": df["v"].astype(float)})
    return out


def from_yfinance(symbol: str, start: datetime) -> pd.DataFrame | None:
    import yfinance as yf
    ticker = XYZ_TO_YF.get(symbol, symbol)  # stock singoli: ticker = symbol stesso
    df = yf.download(ticker, start=start.date(), interval="1h",
                     progress=False, auto_adjust=True)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    df.columns = [str(c).lower() for c in df.columns]
    ts_col = "datetime" if "datetime" in df.columns else "date"
    out = df.rename(columns={ts_col: "ts"})[["ts", "open", "high", "low", "close", "volume"]]
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    return out


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", help="lista crypto esplicita (es. BTC,ETH,SOL); "
                                       "bypassa data/universe.csv — solo Binance→HL, niente xyz")
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc) - timedelta(days=30 * MONTHS)

    report = []
    if args.symbols:
        # override esplicito (es. CI Kronos): fetcha solo il basket dato, via Binance→HL
        for sym in (s.strip() for s in args.symbols.split(",") if s.strip()):
            df = from_binance(sym, start)
            src = "binance"
            if df is None:
                df, src = from_hyperliquid(sym, start), "hyperliquid"
            report.append((sym, src, df))
    else:
        uni = pd.read_csv("data/universe.csv")
        core = uni[(uni.dex == "core") & (uni.kind == "perp")].head(N_CORE)
        xyz = uni[uni.dex == "xyz"].head(N_XYZ)

        for sym in core.symbol:
            df = from_binance(sym, start)
            src = "binance"
            if df is None:
                df, src = from_hyperliquid(sym, start), "hyperliquid"
            report.append((sym, src, df))

        for full in xyz.symbol:
            sym = full.split(":")[1]
            df = from_yfinance(sym, start)
            report.append((full, "yfinance", df))

    print(f"{'symbol':<14} {'fonte':<12} {'candele':>8}  range")
    for sym, src, df in report:
        if df is None or df.empty:
            print(f"{sym:<14} {src:<12} {'FALLITO':>8}", file=sys.stderr)
            continue
        safe = sym.replace(":", "_").replace("/", "_")
        df.to_parquet(DATA_DIR / f"{safe}.parquet", index=False)
        print(f"{sym:<14} {src:<12} {len(df):>8}  {df.ts.min():%Y-%m-%d} → {df.ts.max():%Y-%m-%d}")


if __name__ == "__main__":
    main()
