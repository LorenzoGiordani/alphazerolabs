"""X (Twitter) API v2 come fonte di burst news — stesso schema di pipeline/gdelt.

Il desk geopolitico si attiva su BURST: (ts, topic, z, tone). GDELT misura il
volume di copertura mediatica; qui usiamo l'endpoint COUNTS di X (volume tweet per
ora per query) come segnale parallelo. Stessa semantica, stesso schema → si fonde
con i burst GDELT in geopolitics_paper.active_bursts.

Auth: bearer token app-only in env X_BEARER_TOKEN (tier che abilita counts/recent).
Nessun token o errore API → ritorna None: il segnale degrada a neutro, mai blocca
il trading (come il deadline di gdelt). tone non c'è (counts non dà sentiment) → None.

ponytail: verificare query-syntax e schema risposta contro l'API live quando ci sono
le chiavi; la logica z-score→burst è coperta dal self-check in fondo (uv run pipeline/xnews.py).
"""

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

COUNTS_URL = "https://api.x.com/2/tweets/counts/recent"   # recent = ultimi 7 giorni
PACE_S = 2

# stessi bucket/topic di gdelt.TOPICS, tradotti nella query-syntax di X.
# -is:retweet evita di contare gli stessi contenuti N volte; lang:en allinea a GDELT.
TOPICS = {
    "crypto": "(bitcoin OR ethereum OR crypto OR cryptocurrency) lang:en -is:retweet",
    "fed_macro": '("federal reserve" OR "interest rate" OR inflation OR CPI OR FOMC) lang:en -is:retweet',
    "commodities": '("gold price" OR "oil price" OR OPEC OR "crude oil" OR "natural gas") lang:en -is:retweet',
    "equities": '("stock market" OR "S&P 500" OR nasdaq OR "wall street") lang:en -is:retweet',
    "geopolitics": "(war OR sanctions OR conflict OR military) (market OR economy) lang:en -is:retweet",
}

_CACHE = Path(__file__).resolve().parent.parent / "data" / "news" / "x_live.parquet"
CACHE_TTL_MIN = 60
_COLS = ["ts", "topic", "z", "tone"]


def _token() -> str | None:
    return os.environ.get("X_BEARER_TOKEN") or None


def counts(query: str, start: datetime, end: datetime, deadline: float | None = None) -> pd.DataFrame | None:
    """Volume tweet orario per `query` su [start, end] — colonne (ts, vol).
    None su token assente / errore / deadline (fail-fast, mai blocca)."""
    tok = _token()
    if not tok:
        return None
    rows = []
    nxt = None
    for _ in range(10):   # paginazione capata: 7g orari ≈ 168 bucket, 1 pagina basta
        if deadline is not None and time.monotonic() > deadline:
            break
        params = {
            "query": query, "granularity": "hour",
            "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_time": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if nxt:
            params["next_token"] = nxt
        try:
            r = requests.get(COUNTS_URL, params=params, timeout=30,
                             headers={"Authorization": f"Bearer {tok}"})
        except requests.RequestException as e:
            print(f"  x counts retry: {e}", flush=True)
            return None
        if r.status_code != 200:
            print(f"  x counts HTTP {r.status_code}: {r.text[:160]}", flush=True)
            return None
        body = r.json()
        for b in body.get("data", []):
            rows.append({"ts": pd.Timestamp(b["start"]).tz_localize(None),
                         "vol": float(b.get("tweet_count", 0))})
        nxt = (body.get("meta") or {}).get("next_token")
        if not nxt:
            break
        time.sleep(PACE_S)
    if not rows:
        return None
    return pd.DataFrame(rows).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def x_events_live(days: int = 7, min_z: float = 2.0) -> pd.DataFrame | None:
    """Burst di chiacchiericcio X negli ultimi `days` giorni — (ts, topic, z, tone).
    days capato a 7 dall'endpoint recent. Baseline = media/std della finestra stessa
    (conservativo: i burst la alzano), identico a gdelt.news_events_live."""
    tok = _token()
    if not tok:
        print("  x: nessun X_BEARER_TOKEN → segnale neutro", flush=True)
        return None
    deadline = time.monotonic() + 80
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=min(days, 7))
    out = []
    for topic, query in TOPICS.items():
        if time.monotonic() > deadline:
            print("  x: deadline raggiunta, degrado a neutro", flush=True)
            break
        df = counts(query, start, end, deadline)
        if df is None or df.empty:
            continue
        sd = df["vol"].std()
        if not sd or pd.isna(sd):
            continue
        zs = (df["vol"] - df["vol"].mean()) / sd
        last = None
        for i in zs[zs > min_z].index:
            ts = df.loc[i, "ts"]
            if last is not None and (ts - last) < pd.Timedelta(hours=48):
                last = ts
                continue
            out.append({"ts": ts, "topic": topic, "z": float(zs[i]), "tone": None})
            last = ts
    return pd.DataFrame(out).sort_values("ts").reset_index(drop=True) if out else None


def x_events_cached(days: int = 7, ttl_min: int = CACHE_TTL_MIN) -> pd.DataFrame | None:
    """x_events_live memoizzato su file (TTL), come gdelt.news_events_cached: un solo
    fetch X per finestra TTL, anche se degrada a vuoto (meglio sopprimere il gate ≤1h
    che bruciare rate-limit/credito X)."""
    if _CACHE.exists() and (time.time() - _CACHE.stat().st_mtime) < ttl_min * 60:
        df = pd.read_parquet(_CACHE)
        return df if not df.empty else None
    ev = x_events_live(days=days, min_z=2.0)
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    (ev if ev is not None else pd.DataFrame(columns=_COLS)).to_parquet(_CACHE, index=False)
    return ev


def _demo() -> None:
    """Self-check offline della logica z-score→burst (niente rete/credenziali)."""
    # serie piatta con UN picco → deve emettere esattamente 1 burst su quel ts
    idx = pd.date_range("2026-06-01", periods=100, freq="h")
    vol = [10.0] * 100
    vol[50] = 200.0
    df = pd.DataFrame({"ts": idx, "vol": vol})
    sd = df["vol"].std()
    zs = (df["vol"] - df["vol"].mean()) / sd
    bursts = [df.loc[i, "ts"] for i in zs[zs > 2.0].index]
    assert bursts == [idx[50]], f"atteso 1 burst su idx[50], ottenuto {bursts}"
    # serie piatta → nessun burst
    flat = pd.DataFrame({"ts": idx, "vol": [10.0] * 100})
    zf = (flat["vol"] - flat["vol"].mean()) / (flat["vol"].std() or 1)
    assert list(zf[zf > 2.0].index) == [], "serie piatta non deve dare burst"
    print("xnews self-check OK")


if __name__ == "__main__":
    import sys
    if "--refresh" in sys.argv:
        ev = x_events_cached(ttl_min=0)   # forza il refresh (per il workflow di precompute)
        print(f"x_live.parquet: {0 if ev is None else len(ev)} burst")
    else:
        _demo()
