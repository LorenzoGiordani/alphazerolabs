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
from pipeline.live import atomic_write_parquet  # noqa: E402
from scripts.fetch_coinalyze import api_key, perp_symbols, aggregate, get  # noqa: E402

OUT_DIR = ROOT / "data/coinalyze_1h"
REQUIRED_COLUMNS = {"ts", "liq_long", "liq_short", "oi"}


def hourly_frame(liq: pd.DataFrame, oi: pd.DataFrame) -> pd.DataFrame:
    """Usa l'OI come clock orario; nessun evento di liquidazione vale zero."""
    if oi.empty:
        raise ValueError("open interest 1h assente")
    frame = oi.copy() if liq.empty else oi.merge(liq, on="ts", how="left")
    for column in ("liq_long", "liq_short"):
        if column not in frame:
            frame[column] = 0.0
        else:
            frame[column] = frame[column].fillna(0.0)
    return frame[["ts", "liq_long", "liq_short", "oi"]]


def validate_output(symbols: list[str], *, out_dir: Path = OUT_DIR,
                    max_age_h: float = 8, now=None) -> list[str]:
    """Controlla il contratto realmente consumato da LIQIMB."""
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    errors = []
    for coin in symbols:
        path = out_dir / f"{coin}.parquet"
        try:
            df = pd.read_parquet(path)
        except Exception as exc:
            errors.append(f"{coin}: parquet assente/illeggibile ({exc})")
            continue
        if not REQUIRED_COLUMNS.issubset(df.columns) or df.empty:
            errors.append(f"{coin}: schema/storico incompleto")
            continue
        last = pd.to_datetime(df.ts, utc=True, errors="coerce").max()
        age_h = (now - last).total_seconds() / 3600
        if pd.isna(last) or age_h < -1 or age_h > max_age_h:
            errors.append(f"{coin}: stale ({age_h:.1f}h > {max_age_h:g}h)")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--lookback-days", type=int, default=75, help="finestra da ripullire (≤ retention 1h)")
    args = ap.parse_args()
    requested = [coin.strip() for coin in args.symbols.split(",") if coin.strip()]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["api_key"] = api_key()
    markets = get(s, "future-markets", None)
    to = int(time.time())
    frm = to - args.lookback_days * 86400

    for coin in requested:
        syms = perp_symbols(markets, coin)
        if not syms:
            print(f"  {coin}: nessun perp")
            continue
        common = {"symbols": ",".join(syms), "interval": "1hour", "from": frm, "to": to}
        liq = aggregate(get(s, "liquidation-history", {**common, "convert_to_usd": "true"}),
                        {"liq_long": "l", "liq_short": "s"})
        oi = aggregate(get(s, "open-interest-history", {**common, "convert_to_usd": "true"}),
                       {"oi": "c"})
        df = hourly_frame(liq, oi)
        path = OUT_DIR / f"{coin}.parquet"
        if path.exists():
            df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
        df = df.drop_duplicates(subset=["ts"], keep="last").sort_values("ts")
        atomic_write_parquet(df, path)   # storico non rigenerabile: mai troncato a metà scrittura
        span = f"{df.ts.min():%Y-%m-%d}→{df.ts.max():%Y-%m-%d}"
        print(f"  {coin}: {len(df)} ore accumulate ({span}) → data/coinalyze_1h/{coin}.parquet")

    errors = validate_output(requested)
    if errors:
        for error in errors:
            print(f"  ERRORE {error}", file=sys.stderr)
        raise SystemExit(f"coverage Coinalyze 1h fallita: {len(errors)}/{len(requested)}")


if __name__ == "__main__":
    main()
