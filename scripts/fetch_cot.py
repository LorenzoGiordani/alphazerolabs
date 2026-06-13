"""COT CFTC (Commitments of Traders) per le commodities dell'universo.

Posizionamento "managed money" (hedge fund) dal report Disaggregated — l'analogo
del funding per le commodities: estremi di net positioning = crowding.
Fonte: Socrata publicreporting.cftc.gov, gratis, no key. Aggiornato il venerdì.

Output: data/cot/<simbolo>.parquet — ts (report date), net_mm, oi, net_pct_oi
Uso: .venv/bin/python scripts/fetch_cot.py [--months 14]
"""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "cot"

API = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"  # disaggregated futures only

# simbolo HL (xyz_) → market_and_exchange_names CFTC
MARKETS = {
    "xyz_GOLD": "GOLD - COMMODITY EXCHANGE INC.",
    "xyz_SILVER": "SILVER - COMMODITY EXCHANGE INC.",
    "xyz_CL": "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE",
    "xyz_NATGAS": "NAT GAS NYME - NEW YORK MERCANTILE EXCHANGE",
}
# WTI: il mercato principale è NYMEX — si prova prima quello, poi ICE
WTI_NYMEX = "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE"


def fetch_market(name: str, since: str) -> pd.DataFrame | None:
    r = requests.get(API, params={
        "$where": f"market_and_exchange_names = '{name}' AND report_date_as_yyyy_mm_dd >= '{since}'",
        "$select": "report_date_as_yyyy_mm_dd, m_money_positions_long_all, "
                   "m_money_positions_short_all, open_interest_all",
        "$order": "report_date_as_yyyy_mm_dd", "$limit": 200}, timeout=30)
    rows = r.json()
    if not isinstance(rows, list) or not rows:
        return None
    df = pd.DataFrame({
        "ts": pd.to_datetime([x["report_date_as_yyyy_mm_dd"] for x in rows]),
        "long_mm": [float(x["m_money_positions_long_all"]) for x in rows],
        "short_mm": [float(x["m_money_positions_short_all"]) for x in rows],
        "oi": [float(x["open_interest_all"]) for x in rows]})
    df["net_mm"] = df.long_mm - df.short_mm
    df["net_pct_oi"] = df.net_mm / df.oi.replace(0, pd.NA)
    return df[["ts", "net_mm", "oi", "net_pct_oi"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=14)
    args = ap.parse_args()
    since = (datetime.now(timezone.utc) - timedelta(days=30 * args.months)).strftime("%Y-%m-%d")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for sym, market in MARKETS.items():
        df = fetch_market(market, since)
        if (df is None or df.empty) and sym == "xyz_CL":
            df = fetch_market(WTI_NYMEX, since)
        if df is None or df.empty:
            print(f"{sym}: nessun dato per '{market}'")
            continue
        df.to_parquet(OUT_DIR / f"{sym}.parquet", index=False)
        print(f"{sym}: {len(df)} report, ultimo {df.ts.iloc[-1].date()} "
              f"net_pct_oi {df.net_pct_oi.iloc[-1]:+.3f}")


if __name__ == "__main__":
    main()
