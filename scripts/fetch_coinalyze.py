"""Scarica liquidazioni + OI storici da Coinalyze (API gratuita) → data/coinalyze/<COIN>.parquet.

Coinalyze aggrega liquidazioni/OI/funding multi-exchange. Endpoint liquidation-history
ritorna per simbolo {t, l (long liq), s (short liq)} in USD. Aggreghiamo su tutti i
perp di una coin → liquidazioni long/short totali per giorno.

Retention: daily = storico pieno (~8+ mesi). Intraday solo ~ultimi 2.5 mesi → usiamo daily.
Rate limit 40 chiamate/min (ogni simbolo nel batch consuma 1 chiamata) → throttling.

Anti-lookahead: dato giornaliero, il segnale fa merge_asof backward sulle candele.

Key: COINALYZE_API_KEY in env o in .env (non versionato).
Uso:  .venv/bin/python scripts/fetch_coinalyze.py --symbols BTC,ETH,SOL --months 7
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.live import atomic_write_text

OUT_DIR = ROOT / "data/coinalyze"
BASE = "https://api.coinalyze.net/v1"


def historical_snapshot_fresh(out_dir: Path, symbols: list[str], max_age_hours: float,
                              *, months: int | None = None,
                              now: datetime | None = None) -> bool:
    """True solo se meta e parquet coprono tutti i simboli richiesti e sono freschi."""
    if max_age_hours <= 0:
        return False
    try:
        meta = json.loads((out_dir / "_meta.json").read_text(encoding="utf-8"))
        asof = datetime.fromisoformat(str(meta["asof"]).replace("Z", "+00:00"))
        if asof.tzinfo is None:
            return False
        age = ((now or datetime.now(timezone.utc)) - asof.astimezone(timezone.utc)).total_seconds()
        covered = set(meta["symbols"])
        covered_months = int(meta.get("months", 0))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    requested = set(symbols)
    return (-300 <= age <= max_age_hours * 3600
            and requested <= covered
            and (months is None or covered_months >= months)
            and all((out_dir / f"{symbol}.parquet").is_file() for symbol in requested))


def api_key() -> str:
    k = os.environ.get("COINALYZE_API_KEY")
    if not k:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("COINALYZE_API_KEY="):
                    k = line.split("=", 1)[1].strip()
    if not k:
        raise SystemExit("COINALYZE_API_KEY mancante (env o .env)")
    return k


def get(session, path, params):
    for _ in range(6):
        r = session.get(f"{BASE}/{path}", params=params, timeout=40)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", 5)) + 1)
            continue
        r.raise_for_status()
        n = len(str(params.get("symbols", "")).split(",")) if params else 1
        time.sleep(n * 1.6)  # rate limit 40/min: ogni simbolo = 1 call
        return r.json()
    raise SystemExit("troppi 429 da Coinalyze")


def perp_symbols(markets: list, coin: str) -> list[str]:
    return [m["symbol"] for m in markets
            if m.get("base_asset") == coin and m.get("is_perpetual")
            and m.get("quote_asset") in ("USDT", "USD", "USDC")][:10]


def aggregate(series: list, fields: dict) -> pd.DataFrame:
    """Somma i campi richiesti per timestamp su tutte le serie (exchange)."""
    agg: dict = {}
    for s in series:
        for p in s.get("history", []):
            row = agg.setdefault(p["t"], {k: 0.0 for k in fields})
            for out_k, in_k in fields.items():
                row[out_k] += float(p.get(in_k, 0) or 0)
    if not agg:
        return pd.DataFrame()
    df = pd.DataFrame([{"ts": pd.to_datetime(t, unit="s", utc=True), **v} for t, v in sorted(agg.items())])
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True, help="coin crypto, es. BTC,ETH,SOL")
    ap.add_argument("--months", type=int, default=7)
    ap.add_argument("--if-fresh-hours", type=float, default=0,
                    help="salta rete e API key se lo snapshot completo e' piu recente")
    args = ap.parse_args()
    symbols = [coin.strip().upper() for coin in args.symbols.split(",") if coin.strip()]
    if not symbols:
        raise SystemExit("--symbols non puo essere vuoto")
    if args.months <= 0 or args.if_fresh_hours < 0:
        raise SystemExit("--months deve essere >0 e --if-fresh-hours >=0")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if historical_snapshot_fresh(OUT_DIR, symbols, args.if_fresh_hours, months=args.months):
        print(f"  Coinalyze daily: snapshot fresco per {len(symbols)} simboli, skip")
        return
    s = requests.Session(); s.headers["api_key"] = api_key()
    markets = get(s, "future-markets", None)
    to = int(time.time()); frm = to - (args.months * 31 + 5) * 86400

    completed, failed = [], []
    for coin in symbols:
        syms = perp_symbols(markets, coin)
        if not syms:
            print(f"  {coin}: nessun perp su Coinalyze"); failed.append(coin); continue
        common = {"symbols": ",".join(syms), "interval": "daily", "from": frm, "to": to}
        liq = aggregate(get(s, "liquidation-history", {**common, "convert_to_usd": "true"}),
                        {"liq_long": "l", "liq_short": "s"})
        oi = aggregate(get(s, "open-interest-history", {**common, "convert_to_usd": "true"}),
                       {"oi": "c"})  # OHLC OI: 'c' = close
        if liq.empty:
            print(f"  {coin}: nessuna liquidazione"); failed.append(coin); continue
        df = liq.merge(oi, on="ts", how="left") if not oi.empty else liq
        df.to_parquet(OUT_DIR / f"{coin}.parquet", index=False)
        completed.append(coin)
        tot = df["liq_long"].sum() + df["liq_short"].sum()
        long_dom = df["liq_long"].sum() / tot * 100 if tot else 0
        print(f"  {coin}: {len(df)} giorni ({df.ts.min().date()}→{df.ts.max().date()}), "
              f"long-liq {long_dom:.0f}% del totale → data/coinalyze/{coin}.parquet")
    if failed:
        raise SystemExit(f"snapshot Coinalyze incompleto; simboli falliti: {','.join(failed)}")
    atomic_write_text(OUT_DIR / "_meta.json", json.dumps({
        "source_url": BASE,
        "asof": datetime.now(timezone.utc).isoformat(),
        "symbols": sorted(completed),
        "months": args.months,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
