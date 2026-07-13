"""Executor paper per le decisioni della pipeline agenti (account "agents-v1").

Ogni run (cron, insieme a paper_trade):
1. aggiorna le posizioni aperte (stop/target/time-stop su candele reali)
2. ingerisce soltanto decisioni Codex ammesse (receipt checker, non scadute,
   risk approve/reduce) e apre le posizioni entro i limiti deterministici.

Con ``--manage-only`` esegue soltanto il punto 1: serve quando il generatore LLM
è disattivato e impedisce che una vecchia decisione rimasta in coda apra una
nuova posizione.

Balance fittizio 10k$, dati e prezzi reali. Stesse fee/slippage dell'engine.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.engine import DEFAULT_SLIPPAGE, HL_TAKER_FEE
from backtest.risk import atr_pct
from pipeline.live import atomic_write_text, canonical_symbol, fetch_live
from scripts.decide import HARD_LIMITS, hard_check
from scripts.paper_trade import STATE_FILE, log_event, update_position

# Account che esegue + SORGENTE delle decisioni che consuma. Le decisioni del desk
# agents storico NON portano campo "strategy" → appartengono per default a "agents-v1".
# --source permette a una variante di RIUSARE quelle decisioni (es. agents-rr2-v1
# --source agents-v1 --target-r 2.0 = A/B sull'RR, stesse entry, zero LLM extra).
# Senza --source, un account consuma SOLO le decisioni taggate col proprio id (es.
# claude-strategy-v1 esegue solo ciò che scrive claude_strategy.py, non il backlog).
ACCOUNT = "agents-v1"
SOURCE = "agents-v1"        # da quale strategia provengono le decisioni da eseguire
TARGET_R = None             # None = usa il target_r proposto dall'LLM (comportamento storico)
DECISIONS = ROOT / "paper/decisions.jsonl"
MAX_CONCURRENT = HARD_LIMITS["max_concurrent_positions"]


def _matches_source(d: dict, source: str) -> bool:
    """Una decisione appartiene a `source`. Le decisioni senza tag sono del desk
    storico agents-v1; quelle taggate (claude-strategy-v1, geopolitics-v1) solo del
    proprio id. Evita che un account mangi il backlog di un altro."""
    return d.get("strategy", "agents-v1") == source


def pending_decisions(after_ts: str) -> list[dict]:
    if not DECISIONS.exists():
        return []
    out = []
    for line in DECISIONS.read_text().splitlines():
        d = json.loads(line)
        if d.get("stage") != "final" or d.get("logged_at", "") <= after_ts:
            continue
        if not _matches_source(d, SOURCE):
            continue
        p = d.get("proposal", {})
        if p.get("action") != "trade":
            continue
        admission = d.get("admission") or {}
        provenance = d.get("provenance") or {}
        if admission.get("status") != "approved" or admission.get("executable") is not True:
            continue
        if not provenance.get("pack_id") or not provenance.get("decision_sha256") \
                or not provenance.get("checker_run_id"):
            continue
        try:
            expiry = datetime.fromisoformat(str(admission["expires_at"]).replace("Z", "+00:00"))
            if expiry.tzinfo is None or expiry.astimezone(timezone.utc) < datetime.now(timezone.utc):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        risk = d.get("risk") or {}
        verdict = risk.get("verdict")
        try:
            mult = float(risk.get("size_multiplier"))
        except (TypeError, ValueError):
            continue
        if verdict == "approve" and mult != 1.0:
            continue
        if verdict == "reduce" and not 0.0 < mult < 1.0:
            continue
        if verdict not in ("approve", "reduce"):
            continue
        out.append(d)
    return out


def open_from_decision(d: dict, equity: float, open_positions: int = 0) -> dict | None:
    p = d["proposal"]
    symbol = canonical_symbol(p["symbol"])
    admission = d.get("admission") or {}
    provenance = d.get("provenance") or {}
    if (admission.get("status") != "approved" or admission.get("executable") is not True
            or not provenance.get("pack_id") or not provenance.get("decision_sha256")
            or not provenance.get("checker_run_id")):
        log_event({"type": "skip", "strategy": ACCOUNT, "symbol": symbol,
                   "reason": "decisione priva di admission Codex approvata"})
        return None
    try:
        expiry = datetime.fromisoformat(str(admission["expires_at"]).replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry.astimezone(timezone.utc) < datetime.now(timezone.utc):
            raise ValueError("expired")
    except (KeyError, TypeError, ValueError):
        log_event({"type": "skip", "strategy": ACCOUNT, "symbol": symbol,
                   "reason": "admission Codex scaduta o senza timezone"})
        return None
    try:
        data = fetch_live(symbol, lookback_h=50)
    except Exception as e:
        print(f"  {symbol}: fetch fallito ({e})", file=sys.stderr)
        return None
    last = data["candles"].iloc[-1]
    errs = hard_check(dict(p), open_positions=open_positions,
                      atr_by_symbol={symbol: float(atr_pct(data["candles"]).iloc[-1]) * 100},
                      allow_sizing_bypass=False)
    if errs:
        log_event({"type": "skip", "strategy": ACCOUNT, "symbol": symbol,
                   "reason": f"hard limits: {errs}"})
        return None
    sign = 1 if p["direction"] == "long" else -1
    stop_pct = float(p["stop_pct"]) / 100
    mult = float(d["risk"]["size_multiplier"])
    exposure = min(float(p["leverage"]), float(p["risk_pct"]) * mult / float(p["stop_pct"]))
    px = float(last.close) * (1 + sign * DEFAULT_SLIPPAGE)
    reference = float(admission.get("reference_price") or 0)
    max_drift = float(admission.get("max_price_drift_pct") or 0)
    drift_pct = abs(float(last.close) / reference - 1) * 100 if reference > 0 else float("inf")
    if not 0 < max_drift <= 8 or drift_pct > max_drift:
        log_event({"type": "skip", "strategy": ACCOUNT, "symbol": symbol,
                   "reason": f"price drift {drift_pct:.2f}% > {max_drift:.2f}%"})
        return None
    size_usd = round(exposure * equity, 2)
    volume = float(admission.get("volume_24h_usd") or 0)
    if volume <= 0 or size_usd > 0.005 * volume:
        log_event({"type": "skip", "strategy": ACCOUNT, "symbol": symbol,
                   "reason": "size oltre 0.5% del volume 24h congelato"})
        return None
    target_r = TARGET_R if TARGET_R is not None else float(p["target_r"])   # override RR (variante A/B)
    pos = {
        "strategy": ACCOUNT, "symbol": symbol, "direction": p["direction"],
        "entry_px": px, "size_usd": size_usd,
        "stop_px": px * (1 - sign * stop_pct),
        "target_px": px * (1 + sign * stop_pct * target_r),
        "opened_at": str(last.ts), "checked_until": str(last.ts),
        # fallback 96h se l'LLM omette/emette 0 → time_stop 0 uscirebbe a OGNI candela
        # (>=0h è sempre vero). Stesso fix del desk geopolitics (consistenza).
        "time_stop_h": int(p.get("time_stop_h") or 96),
        "thesis": p["thesis"], "invalidation": p["invalidation"],
        "decision_ts": d["logged_at"],
        "pack_id": provenance["pack_id"],
        "decision_sha256": provenance["decision_sha256"],
    }
    log_event({"type": "open", **pos})
    print(f"  OPEN {symbol} {p['direction']} @ {px:.4g}, size {pos['size_usd']}$ "
          f"(risk verdict: {d['risk']['verdict']} ×{mult})")
    return pos


def main() -> None:
    global ACCOUNT, SOURCE, TARGET_R
    ap = argparse.ArgumentParser(description="Executor paper decisioni desk agenti")
    ap.add_argument("--account", default=ACCOUNT, help="account paper (default agents-v1)")
    ap.add_argument("--source", default=None,
                    help="sorgente decisioni da eseguire (default = l'account stesso; "
                         "es. --source agents-v1 per riusare le decisioni del desk storico)")
    ap.add_argument("--target-r", type=float, default=None,
                    help="forza l'RR all'esecuzione (variante A/B; default = RR proposto dall'LLM)")
    ap.add_argument("--manage-only", action="store_true",
                    help="aggiorna/chiude le posizioni esistenti senza aprire nuove decisioni")
    args = ap.parse_args()
    ACCOUNT, TARGET_R = args.account, args.target_r
    SOURCE = args.source or ACCOUNT

    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    st = state.setdefault(ACCOUNT, {"equity": 10_000.0, "positions": {}, "last_decision_ts": ""})
    print(f"agents paper run {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC — equity {st['equity']:.2f}$")

    # 0. migra chiavi legacy non canoniche (es. "ETH/USDT" scritte prima del fix
    # canonical_symbol): fetch_live sulla chiave raw fallirebbe a ogni run e il
    # time-stop non verrebbe mai valutato (posizione zombie).
    for k in list(st["positions"]):
        ck = canonical_symbol(k)
        if ck and ck != k and ck not in st["positions"]:
            print(f"  migro chiave posizione {k!r} → {ck!r}")
            st["positions"][ck] = st["positions"].pop(k)

    # 1. aggiorna posizioni aperte
    for symbol in list(st["positions"]):
        pos = st["positions"][symbol]
        try:
            data = fetch_live(symbol, lookback_h=200)
        except Exception as e:
            print(f"  {symbol}: fetch fallito ({e})", file=sys.stderr)
            continue
        pos, st["equity"] = update_position(pos, data["candles"], pos["time_stop_h"],
                                            st["equity"], data.get("forming"))
        if pos:
            st["positions"][symbol] = pos
        else:
            del st["positions"][symbol]

    # 2. esegui decisioni nuove
    decisions = [] if args.manage_only else pending_decisions(st["last_decision_ts"])
    for d in decisions:
        st["last_decision_ts"] = max(st["last_decision_ts"], d["logged_at"])
        # ponytail: normalizza PRIMA del check, altrimenti "ETH/USD" non vede la
        # posizione "ETH" già aperta e la riapre come duplicato (bug latente:
        # il check usava il symbol raw della proposal, la key dict invece è canonical).
        symbol = canonical_symbol(d["proposal"]["symbol"])
        if symbol in st["positions"] or len(st["positions"]) >= MAX_CONCURRENT:
            log_event({"type": "skip", "strategy": ACCOUNT, "symbol": symbol,
                       "reason": "posizione esistente o max concorrenti"})
            continue
        pos = open_from_decision(d, st["equity"], open_positions=len(st["positions"]))
        if pos:
            st["equity"] -= pos["size_usd"] * HL_TAKER_FEE
            st["positions"][symbol] = pos

    print(f"fine run: equity {st['equity']:.2f}$, posizioni: {list(st['positions']) or 'nessuna'}")
    atomic_write_text(STATE_FILE, json.dumps(state, indent=1, default=str))
    log_event({"type": "heartbeat", "strategy": ACCOUNT, "equity": round(st["equity"], 2),
               "open_positions": len(st["positions"])})


if __name__ == "__main__":
    main()
