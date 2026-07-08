"""EPS trimestrali da SEC EDGAR (XBRL companyconcept) per il desk stock HIP-3.

Fonte primaria gratuita, point-in-time PER COSTRUZIONE: ogni valore porta la
data `filed` del deposito SEC (non restatabile). Serve al segnale PEAD/SUE
(Bernard & Thomas 1989: SUE time-series = EPS_q − EPS_{q−4}, niente consensus
analisti, niente vendor).

Universo: i single-stock US quotati come perp HIP-3 su Hyperliquid (xyz:*)
che depositano 10-Q/10-K (esclusi ADR/foreign private issuer: 20-F non ha
lo stesso calendario né lo stesso schema XBRL).

Output: data/edgar/eps_<TICKER>.parquet (fy, fp, end, val, filed, form)
        + data/edgar/_meta.json (provenance)
Uso: uv run scripts/fetch_edgar.py [--tickers MU,NVDA,...]
Rate limit SEC: max 10 req/s, User-Agent obbligatorio.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "edgar"
UA = {"User-Agent": "AlphaZeroLabs research ita.giordanilorenzo@gmail.com"}
BASE = "https://data.sec.gov"

# single-stock US su HIP-3 xyz con 10-Q/10-K (verificato da data/universe.csv
# 08/07/2026; esclusi: SKHX/SMSN/KIOXIA/ZHIPU (esteri), BABA/NBIS/BB (20-F/40-F),
# SPCX (privata), indici/commodities)
HIP3_US_STOCKS = ("MU,SNDK,INTC,NVDA,MRVL,TSLA,AMD,META,MSFT,GOOGL,AAPL,"
                  "AMZN,ORCL,HOOD,PLTR,MSTR,CRWV,CRCL")


def cik_map() -> dict[str, int]:
    r = requests.get("https://www.sec.gov/files/company_tickers.json",
                     headers=UA, timeout=30)
    r.raise_for_status()
    return {v["ticker"]: v["cik_str"] for v in r.json().values()}


def fetch_eps(cik: int) -> pd.DataFrame:
    url = f"{BASE}/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/EarningsPerShareDiluted.json"
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    rows = r.json()["units"]["USD/shares"]
    df = pd.DataFrame(rows)
    # solo 10-Q/10-K, periodo trimestrale (~90g: i 10-K riportano anche YTD/annual)
    df["start"] = pd.to_datetime(df["start"])
    df["end"] = pd.to_datetime(df["end"])
    days = (df["end"] - df["start"]).dt.days
    q = df[df["form"].isin(["10-Q", "10-K"]) & days.between(80, 100)].copy()
    # stesso trimestre depositato più volte (10-K ripete i Q; ammendments):
    # tieni il PRIMO deposito = il momento in cui il numero è diventato pubblico
    q["filed"] = pd.to_datetime(q["filed"])
    q = (q.sort_values("filed").groupby("end", as_index=False).first()
          .sort_values("end").reset_index(drop=True))
    return q[["fy", "fp", "start", "end", "val", "filed", "form"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default=HIP3_US_STOCKS)
    a = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ciks = cik_map()
    for t in a.tickers.split(","):
        t = t.strip().upper()
        cik = ciks.get(t)
        if not cik:
            print(f"{t}: CIK non trovato, salto")
            continue
        try:
            df = fetch_eps(cik)
        except Exception as e:
            print(f"{t}: errore {type(e).__name__}: {str(e)[:80]}")
            continue
        df.to_parquet(OUT_DIR / f"eps_{t}.parquet", index=False)
        print(f"{t}: {len(df)} trimestri ({df.end.min():%Y-%m} → {df.end.max():%Y-%m}), "
              f"ultimo filed {df.filed.max():%Y-%m-%d}")
        time.sleep(0.15)  # rate limit SEC
    (OUT_DIR / "_meta.json").write_text(json.dumps(
        {"source_url": f"{BASE}/api/xbrl/companyconcept (SEC EDGAR XBRL)",
         "asof": datetime.now(timezone.utc).isoformat()}))


if __name__ == "__main__":
    main()
