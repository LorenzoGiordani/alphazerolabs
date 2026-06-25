"""Sync incrementale del journal (paper/*.jsonl) verso Supabase (Postgres + pgvector).

Trasforma il journal locale (append-only, formato JSONL) nelle tabelle canonicali
di db/schema.sql: trades, decisions, lessons, equity_snapshots. Idempotente:
ogni riga ha una source_key unica (upsert via PostgREST on_conflict), quindi si
può rilanciare a ogni run del cron senza duplicare.

 Trasporto: API REST di Supabase (PostgREST) via requests — nessuna dipendenza
 aggiuntiva. Auth con service_role key (bypassa RLS). Senza credenziali nell'env
 (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY) va in no-op pulito (exit 0), così può
 stare nel cron senza rompere i run cloud/local finché il progetto non è creato.

Setup una-tantum (richiede il tuo login Supabase, non automatizzabile):
  1. supabase login && supabase projects create lux-ai   (oppure dal dashboard)
  2. supabase db push                                     (applica db/schema.sql)
  3. .env:  SUPABASE_URL=https://<ref>.supabase.co
           SUPABASE_SERVICE_ROLE_KEY=eyJ...              (Settings → API)

Uso:
  uv run scripts/sync_supabase.py            # sync + invio
  uv run scripts/sync_supabase.py --dry-run  # stampa il piano, non invia
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
JOURNAL = ROOT / "paper" / "journal.jsonl"
LESSONS = ROOT / "paper" / "lessons.jsonl"


# ─── parsing del journal in righe DB ──────────────────────────────────────────

def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def _ts(val):
    """Normalizza un timestamp (stringa ISO o 'YYYY-MM-DD HH:MM:SS+00:00')."""
    if val is None:
        return None
    return str(val).replace(" ", "T")  # Postgres accetta entrambi, normalizziamo


def map_records(records: list[dict]) -> dict[str, list[dict]]:
    """Trasforma i record del journal in righe per tabella.

    Logica:
    - stream cronologico; per ogni strategia tengo l'ultima equity (da heartbeat)
      per calcolare leverage = size_usd/equity al momento dell'open;
    - un 'open' crea una riga trades (status open); il 'close' successivo con
      stesso (strategy, symbol) la completa (status closed + exit/pnl);
    - 'skip' → decisions (veto/non-trade);
    - 'heartbeat' → equity_snapshots.

    Idempotente: source_key deterministica per riga.
    """
    trades: dict[str, dict] = {}      # source_key -> row
    decisions, snapshots = [], []
    last_equity: dict[str, float] = {}   # strategy -> equity

    for r in records:
        t, strat = r.get("type"), r.get("strategy", "?")
        if t == "heartbeat":
            last_equity[strat] = float(r.get("equity", 0) or 0)
            sk = f"{strat}|{r.get('logged_at')}"
            snapshots.append({
                "source_key": sk, "strategy": strat,
                "ts": _ts(r.get("logged_at")),
                "equity_usd": float(r.get("equity", 0) or 0),
                "open_positions": r.get("open_positions", []),
            })
        elif t == "open":
            sym = r.get("symbol")
            opened = r.get("opened_at")
            sk = f"{strat}|{sym}|{opened}"
            eq = last_equity.get(strat, 10_000.0) or 10_000.0
            size = float(r.get("size_usd", 0) or 0)
            trades[sk] = {
                "source_key": sk, "strategy": strat,
                "symbol": sym,
                "direction": r.get("direction"),
                "size_usd": size,
                "leverage": round(size / eq, 4) if eq else 0.0,
                "entry_px": r.get("entry_px"),
                "stop_px": r.get("stop_px"),
                "target_px": r.get("target_px"),
                "thesis": r.get("thesis", ""),
                "invalidation": r.get("invalidation"),
                "market_context": {k: v for k, v in r.items()
                                   if k not in ("type", "thesis", "logged_at")},
                "risk_decision": "approved",
                "status": "open",
                "opened_at": _ts(opened),
            }
        elif t == "close":
            # completa l'open aperto più recente per (strategy, symbol)
            sym = r.get("symbol")
            prefix = f"{strat}|{sym}|"
            candidates = [k for k in trades if k.startswith(prefix)
                          and trades[k]["status"] == "open"]
            if not candidates:
                continue
            # l'ultimo aperto (ordinato per opened_at desc)
            target = max(candidates, key=lambda k: trades[k].get("opened_at") or "")
            trades[target].update({
                "status": "closed",
                "exit_px": r.get("exit_px"),
                "exit_reason": r.get("reason"),
                "pnl_usd": r.get("pnl_usd"),
                "closed_at": _ts(r.get("ts")),
            })
        elif t == "skip":
            sym = r.get("symbol")
            sk = f"{strat}|{sym}|{r.get('logged_at')}"
            decisions.append({
                "source_key": sk, "strategy": strat, "symbol": sym,
                "reason": r.get("reason"), "logged_at": _ts(r.get("logged_at")),
                "context": {k: v for k, v in r.items() if k != "type"},
            })

    return {"trades": list(trades.values()), "decisions": decisions,
            "equity_snapshots": snapshots}


def map_lessons(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        sk = f"{r.get('trade_key', r.get('symbol', '?'))}|{r.get('logged_at')}"
        rows.append({
            "source_key": sk,
            "symbol": r.get("symbol"),
            "strategy": r.get("strategy"),
            "trade_key": r.get("trade_key"),
            "verdict": r.get("verdict"),
            "lesson": r.get("lesson", ""),
            "tags": r.get("tags", []),
            "pnl_usd": r.get("pnl_usd"),
            "logged_at": _ts(r.get("logged_at")),
        })
    return rows


# ─── trasporto PostgREST ──────────────────────────────────────────────────────

def _upsert(url: str, headers: dict, table: str, rows: list[dict]) -> tuple[int, str]:
    """POST /rest/v1/<table>?on_conflict=source_key con merge-duplicates.
    Ritorna (righe inviate, messaggio)."""
    if not rows:
        return 0, "vuoto"
    h = {**headers, "Prefer": "resolution=merge-duplicates,return=minimal"}
    resp = requests.post(f"{url}/rest/v1/{table}?on_conflict=source_key",
                         headers=h, json=rows, timeout=60)
    if resp.status_code not in (200, 201):
        return len(rows), f"ERRORE {resp.status_code}: {resp.text[:300]}"
    return len(rows), "ok"


def main() -> int:
    dry = "--dry-run" in sys.argv

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not (url and key):
        print("[sync] SUPABASE_URL/SERVICE_ROLE_KEY mancanti — no-op "
              "(crea il progetto + applica db/schema.sql, vedi doc).")
        return 0

    journal = list(_iter_jsonl(JOURNAL))
    lessons = list(_iter_jsonl(LESSONS))
    mapped = map_records(journal)
    mapped_lessons = map_lessons(lessons)
    all_rows = {**mapped, "lessons": mapped_lessons}

    print(f"[sync] {len(journal)} record journal, {len(lessons)} lezioni → "
          f"{ {k: len(v) for k, v in all_rows.items()} }")
    if dry:
        for table, rows in all_rows.items():
            print(f"  {table}: {len(rows)} righe")
        return 0

    headers = {"apikey": key, "Authorization": f"Bearer {key}",
               "Content-Type": "application/json"}
    for table in ("trades", "decisions", "equity_snapshots", "lessons"):
        n, msg = _upsert(url, headers, table, all_rows.get(table, []))
        print(f"  {table:<16} {n:>4} righe  {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
