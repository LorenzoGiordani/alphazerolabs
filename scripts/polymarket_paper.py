"""F7 MVP — Polymarket forecast journal: esperimento di calibrazione, NON trading.

Tesi falsificabile (gate pre-registrato, piano integrazioni Obsidian):
"l'LLM (GLM-5.2, blind sul prezzo) produce probabilità meglio calibrate del
prezzo di mercato". Misura: Brier score su N ≥ 30 mercati risolti.
  - LLM batte il mercato → si valuta un desk (e MiroFish deve battere l'LLM)
  - LLM perde (atteso: il mercato aggrega più informazione) → il desk muore
    prima di nascere, lezione pubblica. Conferma empirica della regola #1.

Design anti-bias:
  - BLIND: il prompt del forecaster NON contiene il prezzo di mercato
  - il prezzo al momento della previsione è salvato come baseline Brier
  - selezione mercati deterministica (binari, liquidi, risoluzione 2-30g)
  - append-only journal paper/polymarket.jsonl, dedup per market_id

Uso:  uv run scripts/polymarket_paper.py predict [--n 5]
      uv run scripts/polymarket_paper.py resolve
      uv run scripts/polymarket_paper.py report
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JOURNAL = ROOT / "paper" / "polymarket.jsonl"
GAMMA = "https://gamma-api.polymarket.com"
MIN_VOL24 = 100_000
MIN_DAYS, MAX_DAYS = 2, 30
N_MIN_VERDICT = 30


def rows() -> list[dict]:
    if not JOURNAL.exists():
        return []
    return [json.loads(l) for l in JOURNAL.read_text().splitlines() if l.strip()]


def append(rec: dict) -> None:
    JOURNAL.parent.mkdir(exist_ok=True)
    with JOURNAL.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def candidate_markets(n: int) -> list[dict]:
    r = requests.get(f"{GAMMA}/markets", timeout=30, params={
        "closed": "false", "limit": 100, "order": "volume24hr", "ascending": "false"})
    r.raise_for_status()
    now = datetime.now(timezone.utc)
    done = {x["market_id"] for x in rows() if x.get("type") == "prediction"}
    out = []
    for m in r.json():
        try:
            if json.loads(m.get("outcomes") or "[]") != ["Yes", "No"]:
                continue
            end = m.get("endDate")
            if not end:
                continue
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            days = (end_dt - now).total_seconds() / 86400
            if not (MIN_DAYS <= days <= MAX_DAYS):
                continue
            if float(m.get("volume24hr") or 0) < MIN_VOL24:
                continue
            p_mkt = float(json.loads(m["outcomePrices"])[0])
            if not (0.03 <= p_mkt <= 0.97):   # quasi-risolti = Brier gratis, fuori
                continue
            if str(m["id"]) in done:
                continue
            out.append({"id": str(m["id"]), "question": m["question"],
                        "description": (m.get("description") or "")[:800],
                        "end_date": end, "p_market": p_mkt})
        except Exception:
            continue
        if len(out) >= n:
            break
    return out


def cmd_predict(n: int) -> None:
    from scripts.decide import _ask_role
    now = datetime.now(timezone.utc)
    for m in candidate_markets(n):
        prompt = (f"OGGI: {now:%Y-%m-%d}\nDOMANDA: {m['question']}\n"
                  f"RISOLUZIONE ENTRO: {m['end_date'][:10]}\n"
                  f"CONTESTO DEL MERCATO:\n{m['description']}")
        try:
            fc = _ask_role("forecaster", prompt)
        except Exception as e:
            print(f"  {m['id']}: LLM fallito ({e})", file=sys.stderr)
            continue
        rec = {"type": "prediction", "ts": now.isoformat(),
               "market_id": m["id"], "question": m["question"],
               "end_date": m["end_date"], "p_market": m["p_market"],
               "p_llm": max(0.0, min(1.0, float(fc["p_yes"]))),
               "rationale": fc.get("rationale"), "base_rate": fc.get("base_rate")}
        append(rec)
        print(f"  {m['question'][:60]}…  mercato {m['p_market']:.2f} | LLM {rec['p_llm']:.2f}")


def cmd_resolve() -> None:
    now = datetime.now(timezone.utc)
    resolved = {x["market_id"] for x in rows() if x.get("type") == "resolution"}
    pend = [x for x in rows() if x.get("type") == "prediction"
            and x["market_id"] not in resolved
            and datetime.fromisoformat(x["end_date"].replace("Z", "+00:00")) < now]
    for p in pend:
        try:
            r = requests.get(f"{GAMMA}/markets/{p['market_id']}", timeout=30)
            r.raise_for_status()
            m = r.json()
            if not m.get("closed"):
                continue   # scaduto ma non ancora risolto ufficialmente
            y = 1.0 if float(json.loads(m["outcomePrices"])[0]) > 0.5 else 0.0
        except Exception as e:
            print(f"  {p['market_id']}: resolve fallito ({e})", file=sys.stderr)
            continue
        append({"type": "resolution", "ts": now.isoformat(),
                "market_id": p["market_id"], "outcome_yes": y,
                "brier_llm": round((p["p_llm"] - y) ** 2, 4),
                "brier_market": round((p["p_market"] - y) ** 2, 4)})
        print(f"  {p['question'][:60]}…  esito {'YES' if y else 'NO'}  "
              f"brier LLM {(p['p_llm']-y)**2:.3f} vs mkt {(p['p_market']-y)**2:.3f}")


def cmd_report() -> None:
    res = [x for x in rows() if x.get("type") == "resolution"]
    preds = [x for x in rows() if x.get("type") == "prediction"]
    n = len(res)
    print(f"previsioni: {len(preds)} | risolte: {n} (gate verdetto: {N_MIN_VERDICT})")
    if not n:
        return
    bl = sum(r["brier_llm"] for r in res) / n
    bm = sum(r["brier_market"] for r in res) / n
    print(f"Brier LLM {bl:.4f} vs mercato {bm:.4f}  "
          f"({'LLM meglio' if bl < bm else 'MERCATO meglio'})")
    if n >= N_MIN_VERDICT:
        verdict = ("LLM batte il mercato -> valutare desk (e MiroFish deve battere l'LLM)"
                   if bl < bm else
                   "FALSIFICATO: l'LLM non batte il prezzo -> niente desk direzionale (conferma regola #1)")
        print(f"VERDETTO (N>={N_MIN_VERDICT}): {verdict}")
    else:
        print(f"campione insufficiente per il verdetto ({n}/{N_MIN_VERDICT})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["predict", "resolve", "report"])
    ap.add_argument("--n", type=int, default=5)
    a = ap.parse_args()
    {"predict": lambda: cmd_predict(a.n),
     "resolve": cmd_resolve, "report": cmd_report}[a.cmd]()


if __name__ == "__main__":
    main()
