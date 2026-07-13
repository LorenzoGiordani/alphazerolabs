"""Layer desk all-symbol per Codex/GPT-5.6, senza API LLM.

Il flusso e' intenzionalmente separato in artefatti revisionabili:

  uv run scripts/codex_desk.py pack --out /tmp/decision-pack.json
  uv run scripts/codex_desk.py prompt --pack /tmp/decision-pack.json
  uv run scripts/codex_desk.py check --pack ... --decision ... [--approval ...]
  uv run scripts/codex_desk.py ingest --pack ... --decision ... --approval ...

``pack`` censisce tutti i perp Hyperliquid ma arricchisce con candele solo un
prefiltro bounded, nel rispetto del budget REST. GPT vede al massimo 12 setup la
cui direzione e' gia fissata dal gate TSMOM; giudica rischio/correlazione, non
inventa il segnale. ``check`` non scrive. ``ingest`` e' l'unica mutazione e
richiede una receipt APPROVE di un checker indipendente.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.risk import atr_pct
from backtest.signals import tsmom
from backtest.walkforward import regimes
from pipeline.live import (atomic_write_text, canonical_symbol, fetch_live_cached,
                           news_headlines, perp_market_snapshot)
from scripts.decide import HARD_LIMITS, hard_check, recall_lessons
from scripts.prompts import get_role, prompts_version


STATE_FILE = ROOT / "paper/state.json"
DECISIONS = ROOT / "paper/decisions.jsonl"
PACK_KIND = "decision-pack.v1"
DECISION_KIND = "codex-decision.v1"
APPROVAL_KIND = "codex-approval.v1"
ACCOUNT = "agents-v1"

# Limite IP ufficiale HL: 1200 weight/min. Ne usiamo al massimo 1000 per
# lasciare margine a posizioni gia aperte e altri processi sullo stesso IP.
HL_WEIGHT_BUDGET = 1000
HL_BASE_INFO_WEIGHT = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_ts(value, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} non e' un timestamp ISO valido") from exc
    if dt.tzinfo is None:
        raise ValueError(f"{field} deve includere timezone")
    return dt.astimezone(timezone.utc)


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def content_hash(value) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _with_pack_id(pack: dict) -> dict:
    payload = {k: v for k, v in pack.items() if k != "pack_id"}
    return {**payload, "pack_id": content_hash(payload)}


def verify_pack(pack: dict) -> None:
    if pack.get("kind") != PACK_KIND:
        raise ValueError(f"kind pack atteso: {PACK_KIND}")
    expected = content_hash({k: v for k, v in pack.items() if k != "pack_id"})
    if pack.get("pack_id") != expected:
        raise ValueError("pack_id non corrisponde al contenuto: pack alterato")


def _repo_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            text=True, capture_output=True, check=True)
    return result.stdout.strip()


def _finite_number(value, field: str, *, gt: float | None = None,
                   ge: float | None = None, le: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} deve essere numerico")
    n = float(value)
    if not math.isfinite(n):
        raise ValueError(f"{field} deve essere finito")
    if gt is not None and n <= gt:
        raise ValueError(f"{field} deve essere > {gt}")
    if ge is not None and n < ge:
        raise ValueError(f"{field} deve essere >= {ge}")
    if le is not None and n > le:
        raise ValueError(f"{field} deve essere <= {le}")
    return n


def _load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def _portfolio_snapshot() -> dict:
    account = _load_state().get(ACCOUNT, {})
    positions = []
    for symbol, pos in sorted((account.get("positions") or {}).items()):
        positions.append({
            "symbol": canonical_symbol(symbol),
            "direction": pos.get("direction"),
            "size_usd": pos.get("size_usd"),
            "entry_px": pos.get("entry_px"),
            "stop_px": pos.get("stop_px"),
            "target_px": pos.get("target_px"),
            "opened_at": pos.get("opened_at"),
        })
    return {
        "account": ACCOUNT,
        "equity": account.get("equity", 10_000.0),
        "open_position_count": len(positions),
        "open_positions": positions,
    }


def _underlying(symbol: str) -> str:
    return symbol.split(":")[-1].upper()


def _deduplicate(rows: list[dict]) -> tuple[list[dict], int]:
    """Una venue per underlying: tiene quella piu liquida, tie-break sul symbol."""
    ordered = sorted(rows, key=lambda r: (-r["volume_24h_usd"], r["symbol"]))
    seen, out = set(), []
    for row in ordered:
        base = _underlying(row["symbol"])
        if base in seen:
            continue
        seen.add(base)
        out.append(row)
    return out, len(rows) - len(out)


def _candle_weight(lookback_h: int) -> int:
    # candleSnapshot: weight base 20 + peso addizionale per 60 item restituiti.
    return HL_BASE_INFO_WEIGHT + math.ceil((lookback_h + 1) / 60)


def _asset_context(row: dict, data: dict, now: datetime) -> dict:
    candles = data["candles"]
    if len(candles) < 721:
        raise ValueError(f"storia insufficiente: {len(candles)} barre, richieste 721")
    asof = _parse_ts(candles.ts.iloc[-1], "candle.asof")
    age_s = max(0.0, (now - asof).total_seconds())
    if age_s > 2.5 * 3600:
        raise ValueError(f"candela stale: eta {age_s / 3600:.1f}h")

    gate = int(tsmom(data).iloc[-1])
    direction = "long" if gate > 0 else "short" if gate < 0 else None
    price = float(candles.close.iloc[-1])
    atr = float(atr_pct(candles).iloc[-1]) * 100
    return {
        "symbol": row["symbol"],
        "dex": row["dex"],
        "direction_from_gate": direction,
        "gate": {"name": "tsmom_168_720", "value": gate, "passed": gate != 0},
        "asof": _iso(asof),
        "data_age_sec": round(age_s),
        "bars": len(candles),
        "price": price,
        "atr_pct": round(atr, 4),
        "change_24h": float(candles.close.iloc[-1] / candles.close.iloc[-25] - 1),
        "change_7d": float(candles.close.iloc[-1] / candles.close.iloc[-169] - 1),
        "regime_7d": str(regimes(candles).iloc[-1]),
        "volume_24h_usd": row["volume_24h_usd"],
        "open_interest_usd": row["open_interest_usd"],
        "funding_hourly": row["funding"],
        "funding_apr": row["funding"] * 24 * 365,
        "max_exchange_leverage": row["max_leverage"],
        "trade_eligible": gate != 0,
        "eligibility_reasons": (["liquidity", "fresh_721h_history", "tsmom_direction_frozen"]
                                if gate else ["tsmom_neutral"]),
    }


def build_pack(*, top: int = 12, prefilter: int = 20,
               min_volume_usd: float = 1_000_000,
               min_oi_usd: float = 500_000, lookback_h: int = 800,
               min_enrichment_coverage: float = 0.90,
               expires_h: float = 2.0, weight_budget: int = HL_WEIGHT_BUDGET) -> dict:
    if not 1 <= top <= 12:
        raise ValueError("top deve essere tra 1 e 12")
    if prefilter < top:
        raise ValueError("prefilter deve essere >= top")
    if lookback_h < 721:
        raise ValueError("lookback_h deve essere >= 721 per il gate TSMOM")
    if not 0 < min_enrichment_coverage <= 1:
        raise ValueError("min_enrichment_coverage deve essere in (0,1]")

    now = _now()
    census = perp_market_snapshot()  # strict: una venue fallita invalida il pack
    if not census:
        raise RuntimeError("snapshot Hyperliquid vuoto")

    open_symbols = {p["symbol"] for p in _portfolio_snapshot()["open_positions"]}
    active = [r for r in census if not r["delisted"]]
    structurally_eligible = [
        r for r in active
        if r["mark"] > 0
        and r["volume_24h_usd"] >= min_volume_usd
        and r["open_interest_usd"] >= min_oi_usd
        # V1: i gate 168/720 sono validati su candele crypto 24/7. I mercati
        # HIP-3 a sessione restano nel census ma non diventano trade finche non
        # esiste un gate calendar-aware validato.
        and r["dex"] == ""
        and r["symbol"] not in open_symbols
    ]
    unique, duplicates_removed = _deduplicate(structurally_eligible)

    dex_count = len({r["dex"] for r in census})
    metadata_weight = HL_BASE_INFO_WEIGHT * (1 + dex_count)  # perpDexs + ogni meta
    per_candle_weight = _candle_weight(lookback_h)
    budget_limit = max(0, (weight_budget - metadata_weight) // per_candle_weight)
    enrich_n = min(prefilter, budget_limit, len(unique))
    if enrich_n < top and len(unique) >= top:
        raise RuntimeError(
            f"budget HL insufficiente: arricchibili {enrich_n}, top richiesto {top}; "
            f"metadata_weight={metadata_weight}, candle_weight={per_candle_weight}")

    attempted = unique[:enrich_n]
    enriched, failures = [], []
    for row in attempted:
        try:
            data = fetch_live_cached(row["symbol"], lookback_h, with_funding=False)
            enriched.append(_asset_context(row, data, now))
        except Exception as exc:
            failures.append({"symbol": row["symbol"], "reason": str(exc)[:240]})

    coverage = len(enriched) / len(attempted) if attempted else 0.0
    if attempted and coverage < min_enrichment_coverage:
        raise RuntimeError(
            f"coverage enrichment {coverage:.1%} < minimo {min_enrichment_coverage:.1%}: {failures}")

    shortlist = [a for a in enriched if a["trade_eligible"]][:top]
    for rank, asset in enumerate(shortlist, 1):
        asset["rank"] = rank

    census_rows = sorted(census, key=lambda r: (r["dex"], r["symbol"]))
    census_sha = content_hash(census_rows)
    portfolio = _portfolio_snapshot()
    excluded = {
        "delisted": sum(bool(r["delisted"]) for r in census),
        "below_volume": sum(not r["delisted"] and r["volume_24h_usd"] < min_volume_usd for r in census),
        "below_open_interest": sum(not r["delisted"] and r["open_interest_usd"] < min_oi_usd for r in census),
        "already_open": sum(r["symbol"] in open_symbols for r in census),
        "hip3_gate_not_validated": sum(not r["delisted"] and r["dex"] != "" for r in census),
        "duplicate_underlying": duplicates_removed,
        "tsmom_neutral_after_enrichment": sum(not a["trade_eligible"] for a in enriched),
        "enrichment_failed": len(failures),
    }
    role = get_role("all_symbol_pm")
    pack = {
        "kind": PACK_KIND,
        "generated_at": _iso(now),
        "expires_at": _iso(now + timedelta(hours=expires_h)),
        "repo_commit": _repo_commit(),
        "prompt_version": prompts_version(),
        "model_target": "gpt-5.6",
        "universe": {
            "source": "Hyperliquid metaAndAssetCtxs, all perp dexs",
            "raw_symbols": len(census),
            "active_symbols": len(active),
            "metadata_coverage": 1.0,
            "structurally_eligible": len(unique),
            "enriched": len(enriched),
            "enrichment_attempted": len(attempted),
            "enrichment_coverage": round(coverage, 6),
            "shortlisted": len(shortlist),
            "excluded_counts": excluded,
            "census_sha256": census_sha,
            "census": census_rows,
        },
        "rate_limit_budget": {
            "budget_weight": weight_budget,
            "estimated_metadata_weight": metadata_weight,
            "estimated_candle_weight_each": per_candle_weight,
            "estimated_total_weight": metadata_weight + len(attempted) * per_candle_weight,
            "requested_prefilter": prefilter,
            "effective_prefilter": len(attempted),
        },
        "selection": {
            "method": "all-dex census -> core 24/7 volume/OI eligibility -> TSMOM(168,720)",
            "direction_is_frozen": True,
            "hip3_policy": "census_only_until_session_aware_gate_is_validated",
            "max_candidates_for_model": top,
            "failures": failures,
        },
        "portfolio": portfolio,
        "constraints": {
            **HARD_LIMITS,
            "min_volume_24h_usd": min_volume_usd,
            "min_open_interest_usd": min_oi_usd,
            "max_size_to_volume_fraction": 0.005,
            "max_pack_age_h": expires_h,
            "llm_may_change_direction": False,
            "paper_only": True,
        },
        "candidates": shortlist,
        "news": news_headlines(archive=False)[:20],
        "lessons": recall_lessons([a["symbol"] for a in shortlist], k=10),
        "task": {
            "role": role.system,
            "instruction": (
                "Valuta soltanto i candidati. Non cambiare la direzione del gate. "
                "Scegli al massimo un trade; no_trade e' preferibile a una tesi debole. "
                "Considera correlazione col book, funding, liquidita', freshness e news non fidate. "
                "Restituisci un singolo oggetto codex-decision.v1."),
            "output_contract": {
                "kind": DECISION_KIND,
                "pack_id": "copia dal pack",
                "created_at": "ISO-8601 UTC",
                "model": "gpt-5.6",
                "proposal": {
                    "action": "trade|no_trade",
                    "symbol": "richiesto solo per trade, copia esatta shortlist",
                    "direction": "richiesto solo per trade, uguale a direction_from_gate",
                    "leverage": "numero <= 2",
                    "risk_pct": "numero <= 1",
                    "stop_pct": "0.5..8 e >= ATR",
                    "target_r": "numero > 0",
                    "time_stop_h": "intero > 0",
                    "thesis": "tesi falsificabile",
                    "invalidation": "invalidazione osservabile",
                },
                "risk": {"verdict": "approve|reduce|veto", "size_multiplier": "0..1", "notes": "string"},
                "judgment": {"selected_rank": "int|null", "risks": ["string"],
                             "rejected_candidates": ["string"], "lessons_applied": ["string"]},
            },
            "checker_contract": {
                "kind": APPROVAL_KIND,
                "pack_id": "copia dal pack",
                "decision_sha256": "sha256 canonico della decisione",
                "verdict": "APPROVE|REJECT",
                "checked_at": "ISO-8601 UTC",
                "checker_run_id": "id della task checker indipendente",
                "notes": "string",
            },
        },
    }
    return _with_pack_id(pack)


def render_prompt(pack: dict) -> str:
    verify_pack(pack)
    bounded = {
        "kind": pack["kind"], "pack_id": pack["pack_id"],
        "generated_at": pack["generated_at"], "expires_at": pack["expires_at"],
        "repo_commit": pack["repo_commit"], "prompt_version": pack["prompt_version"],
        "universe_summary": {k: v for k, v in pack["universe"].items() if k != "census"},
        "portfolio": pack["portfolio"], "constraints": pack["constraints"],
        "candidates": pack["candidates"], "news": pack["news"],
        "lessons": pack["lessons"], "task": pack["task"],
    }
    return (
        "# AlphaZero Labs — decisione desk all-symbol\n\n"
        "Il census completo e il suo hash restano nel pack JSON; sotto compare solo la shortlist bounded.\n\n"
        + _canonical_json(bounded)
    )


def _candidate_map(pack: dict) -> dict[str, dict]:
    return {a["symbol"]: a for a in pack.get("candidates", [])}


def validate_decision(pack: dict, decision: dict, *, now: datetime | None = None) -> dict:
    verify_pack(pack)
    now = (now or _now()).astimezone(timezone.utc)
    if now > _parse_ts(pack["expires_at"], "pack.expires_at"):
        raise ValueError("pack scaduto: rigenerare prima della decisione")
    if decision.get("kind") != DECISION_KIND:
        raise ValueError(f"kind decisione atteso: {DECISION_KIND}")
    if decision.get("pack_id") != pack["pack_id"]:
        raise ValueError("decision.pack_id non corrisponde al pack")
    model = str(decision.get("model", ""))
    if not model.startswith("gpt-5.6"):
        raise ValueError("decision.model deve identificare GPT-5.6")
    created = _parse_ts(decision.get("created_at"), "decision.created_at")
    if created > now + timedelta(minutes=5):
        raise ValueError("decision.created_at e' nel futuro")
    if created < _parse_ts(pack["generated_at"], "pack.generated_at"):
        raise ValueError("decisione precedente al pack")

    proposal = decision.get("proposal")
    risk = decision.get("risk")
    judgment = decision.get("judgment")
    if not isinstance(proposal, dict) or not isinstance(risk, dict) or not isinstance(judgment, dict):
        raise ValueError("proposal, risk e judgment devono essere oggetti")
    for field in ("risks", "rejected_candidates", "lessons_applied"):
        values = judgment.get(field)
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f"judgment.{field} deve essere una lista di stringhe")
    if proposal.get("action") not in ("trade", "no_trade"):
        raise ValueError("proposal.action deve essere trade o no_trade")
    if risk.get("verdict") not in ("approve", "reduce", "veto"):
        raise ValueError("risk.verdict invalido")
    mult = _finite_number(risk.get("size_multiplier"), "risk.size_multiplier", ge=0, le=1)
    if not str(risk.get("notes", "")).strip():
        raise ValueError("risk.notes obbligatorio")

    executable = False
    candidate = None
    if proposal["action"] == "no_trade":
        if judgment.get("selected_rank") is not None:
            raise ValueError("no_trade richiede judgment.selected_rank=null")
        if risk["verdict"] != "veto" or mult != 0:
            raise ValueError("no_trade richiede risk.veto e size_multiplier=0")
        if not str(proposal.get("thesis", "")).strip():
            raise ValueError("no_trade richiede una motivazione in proposal.thesis")
    else:
        symbol = proposal.get("symbol")
        candidate = _candidate_map(pack).get(symbol)
        if candidate is None:
            raise ValueError("symbol non presente nella shortlist congelata")
        if proposal.get("direction") != candidate["direction_from_gate"]:
            raise ValueError("direction diversa dal gate sistematico congelato")
        if judgment.get("selected_rank") != candidate["rank"]:
            raise ValueError("judgment.selected_rank non corrisponde al candidato")
        _finite_number(proposal.get("leverage"), "proposal.leverage", gt=0)
        _finite_number(proposal.get("risk_pct"), "proposal.risk_pct", gt=0)
        _finite_number(proposal.get("stop_pct"), "proposal.stop_pct", gt=0)
        _finite_number(proposal.get("target_r"), "proposal.target_r", gt=0)
        time_stop = proposal.get("time_stop_h")
        if isinstance(time_stop, bool) or not isinstance(time_stop, int) or time_stop <= 0:
            raise ValueError("proposal.time_stop_h deve essere intero > 0")
        if not str(proposal.get("thesis", "")).strip() or not str(proposal.get("invalidation", "")).strip():
            raise ValueError("tesi e invalidazione obbligatorie")
        errs = hard_check(dict(proposal),
                          open_positions=pack["portfolio"]["open_position_count"],
                          atr_by_symbol={symbol: candidate["atr_pct"]},
                          allow_sizing_bypass=False)
        if errs:
            raise ValueError(f"hard limits violati: {errs}")
        if risk["verdict"] == "veto":
            if mult != 0:
                raise ValueError("risk.veto richiede size_multiplier=0")
        elif risk["verdict"] == "reduce":
            if not 0 < mult < 1:
                raise ValueError("risk.reduce richiede 0 < size_multiplier < 1")
            executable = True
        else:
            if mult != 1:
                raise ValueError("risk.approve richiede size_multiplier=1")
            executable = True

    return {
        "pack_id": pack["pack_id"],
        "decision_sha256": content_hash(decision),
        "valid": True,
        "executable": executable,
        "symbol": candidate["symbol"] if candidate else None,
    }


def validate_approval(pack: dict, decision: dict, approval: dict,
                      *, now: datetime | None = None) -> dict:
    current = (now or _now()).astimezone(timezone.utc)
    receipt = validate_decision(pack, decision, now=current)
    if approval.get("kind") != APPROVAL_KIND:
        raise ValueError(f"kind approval atteso: {APPROVAL_KIND}")
    if approval.get("pack_id") != pack["pack_id"]:
        raise ValueError("approval.pack_id non corrisponde al pack")
    if approval.get("decision_sha256") != receipt["decision_sha256"]:
        raise ValueError("approval.decision_sha256 non corrisponde alla decisione")
    if approval.get("verdict") != "APPROVE":
        raise ValueError("checker non ha emesso APPROVE")
    if not str(approval.get("checker_run_id", "")).strip():
        raise ValueError("checker_run_id obbligatorio")
    checked = _parse_ts(approval.get("checked_at"), "approval.checked_at")
    if checked > current + timedelta(minutes=5):
        raise ValueError("approval.checked_at e' nel futuro")
    if checked < _parse_ts(decision["created_at"], "decision.created_at"):
        raise ValueError("approval precedente alla decisione")
    if checked > _parse_ts(pack["expires_at"], "pack.expires_at"):
        raise ValueError("approval prodotta dopo la scadenza del pack")
    return {**receipt, "checker_run_id": approval["checker_run_id"]}


def ingest(pack: dict, decision: dict, approval: dict) -> dict:
    receipt = validate_approval(pack, decision, approval)
    existing = DECISIONS.read_text().splitlines() if DECISIONS.exists() else []
    for line in existing:
        row = json.loads(line)
        if row.get("provenance", {}).get("decision_sha256") == receipt["decision_sha256"]:
            return {**receipt, "ingested": False, "reason": "duplicate"}

    proposal = dict(decision["proposal"])
    if proposal.get("symbol"):
        proposal["symbol"] = canonical_symbol(proposal["symbol"])
    candidate = _candidate_map(pack).get(proposal.get("symbol"), {})
    record = {
        "stage": "final",
        "strategy": ACCOUNT,
        "proposal": proposal,
        "risk": decision["risk"],
        "judgment": decision["judgment"],
        "admission": {
            "status": "approved",
            "executable": receipt["executable"],
            "expires_at": pack["expires_at"],
            "reference_price": candidate.get("price"),
            "volume_24h_usd": candidate.get("volume_24h_usd"),
            "max_price_drift_pct": min(3.0, max(1.0, candidate.get("atr_pct", 0))),
        },
        "provenance": {
            "pack_id": pack["pack_id"],
            "decision_sha256": receipt["decision_sha256"],
            "repo_commit": pack["repo_commit"],
            "prompt_version": pack["prompt_version"],
            "model": decision["model"],
            "checker_run_id": receipt["checker_run_id"],
        },
        "logged_at": _iso(_now()),
    }
    text = ("\n".join(existing) + ("\n" if existing else "") +
            json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    atomic_write_text(DECISIONS, text)
    return {**receipt, "ingested": True}


def _read_json(path: str) -> dict:
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path}: atteso oggetto JSON")
    return value


def main() -> None:
    ap = argparse.ArgumentParser(description="Desk all-symbol Codex/GPT-5.6")
    sub = ap.add_subparsers(dest="command", required=True)

    pack_ap = sub.add_parser("pack", help="genera census+shortlist all-symbol")
    pack_ap.add_argument("--out", required=True)
    pack_ap.add_argument("--top", type=int, default=12)
    pack_ap.add_argument("--prefilter", type=int, default=20)
    pack_ap.add_argument("--min-volume", type=float, default=1_000_000)
    pack_ap.add_argument("--min-oi", type=float, default=500_000)
    pack_ap.add_argument("--lookback-h", type=int, default=800)

    prompt_ap = sub.add_parser("prompt", help="rende il prompt bounded dal pack")
    prompt_ap.add_argument("--pack", required=True)

    check_ap = sub.add_parser("check", help="valida senza scrivere")
    check_ap.add_argument("--pack", required=True)
    check_ap.add_argument("--decision", required=True)
    check_ap.add_argument("--approval")

    ingest_ap = sub.add_parser("ingest", help="appende una decisione ammessa")
    ingest_ap.add_argument("--pack", required=True)
    ingest_ap.add_argument("--decision", required=True)
    ingest_ap.add_argument("--approval", required=True)

    args = ap.parse_args()
    if args.command == "pack":
        pack = build_pack(top=args.top, prefilter=args.prefilter,
                          min_volume_usd=args.min_volume, min_oi_usd=args.min_oi,
                          lookback_h=args.lookback_h)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(args.out, json.dumps(pack, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        print(json.dumps({"pack": args.out, "pack_id": pack["pack_id"],
                          "scanned": pack["universe"]["raw_symbols"],
                          "shortlisted": pack["universe"]["shortlisted"]}))
    elif args.command == "prompt":
        print(render_prompt(_read_json(args.pack)))
    elif args.command == "check":
        pack, decision = _read_json(args.pack), _read_json(args.decision)
        receipt = (validate_approval(pack, decision, _read_json(args.approval))
                   if args.approval else validate_decision(pack, decision))
        print(json.dumps(receipt, indent=2))
    else:
        result = ingest(_read_json(args.pack), _read_json(args.decision),
                        _read_json(args.approval))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
