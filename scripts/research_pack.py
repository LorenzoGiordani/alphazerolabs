"""Research OS L1: census all-dex e contratti Maker/Checker report-only.

Il modulo non crea strategie, non esegue backtest e non tocca paper state o
journal. Produce un pack content-addressed per GPT-5.6, valida il report del
Daily Maker e la receipt di un Hourly Checker con identita distinta.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.risk import atr_pct
from backtest.signals import tsmom
from backtest.walkforward import regimes
from pipeline.live import (atomic_write_text, canonical_symbol, fetch_candles_cached,
                           news_headlines, perp_market_snapshot)


PACK_KIND = "daily-research-pack.v1"
MAKER_KIND = "daily-research-maker.v1"
CHECKER_KIND = "hourly-independent-checker.v1"
HL_WEIGHT_BUDGET = 1000
HL_BASE_INFO_WEIGHT = 20
FAMILY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
APPROVE_VERDICTS = {"APPROVE_NO_CANDIDATE", "APPROVE_PREREG_ONLY"}
GUARDRAILS = {
    "report_only": True,
    "no_trade": True,
    "no_backtest": True,
    "no_holdout": True,
    "no_strategy_activation": True,
    "no_repo_or_vault_write": True,
}
CHECKS = {
    "pack_integrity", "maker_schema", "identity_separation",
    "inventory_novelty", "source_quality", "data_feasibility",
    "scope_report_only", "checker_no_forbidden_writes",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_ts(value, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} non e' un timestamp ISO valido") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} deve includere timezone")
    return parsed.astimezone(timezone.utc)


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def content_hash(value) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _with_pack_id(pack: dict) -> dict:
    payload = {key: value for key, value in pack.items() if key != "pack_id"}
    return {**payload, "pack_id": content_hash(payload)}


def verify_pack(pack: dict) -> None:
    if not isinstance(pack, dict) or pack.get("kind") != PACK_KIND:
        raise ValueError(f"kind pack atteso: {PACK_KIND}")
    expected = content_hash({key: value for key, value in pack.items() if key != "pack_id"})
    if pack.get("pack_id") != expected:
        raise ValueError("pack_id non corrisponde al contenuto: pack alterato")
    universe = pack.get("universe")
    if not isinstance(universe, dict) or not isinstance(universe.get("census"), list):
        raise ValueError("census mancante dal pack")
    if universe.get("census_sha256") != content_hash(universe["census"]):
        raise ValueError("census_sha256 non corrisponde: census alterato")


def _repo_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            text=True, capture_output=True, check=True)
    return result.stdout.strip()


def _finite(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} deve essere numerico")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} deve essere finito")
    return number


def _expect_keys(value, required: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} deve essere un oggetto")
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise ValueError(f"{label} chiavi invalide; mancanti={sorted(missing)}, extra={sorted(extra)}")
    return value


def _text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve essere una stringa non vuota")
    return value.strip()


def _strings(value, field: str, *, allow_empty: bool = True) -> list[str]:
    if (not isinstance(value, list)
            or any(not isinstance(item, str) or not item.strip() for item in value)
            or (not allow_empty and not value)):
        suffix = " non vuota" if not allow_empty else ""
        raise ValueError(f"{field} deve essere una lista{suffix} di stringhe")
    return value


def _portfolio_snapshot(state_file: str | Path) -> dict:
    path = Path(state_file)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {}
    if not isinstance(state, dict):
        raise ValueError("paper state deve essere un oggetto JSON")
    positions = []
    for account, record in sorted(state.items()):
        if not isinstance(record, dict) or not isinstance(record.get("positions"), dict):
            continue
        for raw_symbol, position in sorted(record["positions"].items()):
            if not isinstance(position, dict):
                continue
            symbol = canonical_symbol(raw_symbol)
            direction = position.get("direction")
            notional = position.get("notional")
            if direction not in ("long", "short") and isinstance(notional, (int, float)):
                direction = "long" if notional >= 0 else "short"
            size = position.get("size_usd", abs(notional) if isinstance(notional, (int, float)) else None)
            positions.append({
                "account": str(account), "symbol": symbol,
                "direction": direction if direction in ("long", "short") else "unknown",
                "size_usd": round(float(size), 2) if isinstance(size, (int, float)) else None,
            })
    return {
        "source": str(path),
        "source_sha256": content_hash(state),
        "open_position_count": len(positions),
        "open_symbols": sorted({row["symbol"] for row in positions}),
        "positions": positions,
    }


def _underlying(symbol: str) -> str:
    return symbol.split(":")[-1].upper()


def _deduplicate(rows: list[dict]) -> tuple[list[dict], int]:
    ordered = sorted(rows, key=lambda row: (-row["volume_24h_usd"], row["symbol"]))
    seen, unique = set(), []
    for row in ordered:
        base = _underlying(row["symbol"])
        if base in seen:
            continue
        seen.add(base)
        unique.append(row)
    return unique, len(rows) - len(unique)


def _candle_weight(lookback_h: int) -> int:
    return HL_BASE_INFO_WEIGHT + math.ceil((lookback_h + 1) / 60)


def _market_context(row: dict, data: dict, now: datetime) -> dict:
    candles = data.get("candles") if isinstance(data, dict) else None
    if candles is None or len(candles) < 721:
        raise ValueError(f"storia insufficiente: {0 if candles is None else len(candles)} barre")
    asof = _parse_ts(candles.ts.iloc[-1], "candle.asof")
    age_seconds = (now - asof).total_seconds()
    if age_seconds < -3600 or age_seconds > 2.5 * 3600:
        raise ValueError(f"candela stale/future: eta {age_seconds / 3600:.1f}h")
    gate = int(tsmom(data).iloc[-1])
    trend_state = "up" if gate > 0 else "down" if gate < 0 else "mixed"
    price = _finite(float(candles.close.iloc[-1]), "price")
    atr = _finite(float(atr_pct(candles).iloc[-1]) * 100, "atr_pct")
    change_24h = _finite(float(candles.close.iloc[-1] / candles.close.iloc[-25] - 1), "change_24h")
    change_7d = _finite(float(candles.close.iloc[-1] / candles.close.iloc[-169] - 1), "change_7d")
    return {
        "symbol": row["symbol"], "dex": row["dex"],
        "asof": _iso(asof), "data_age_sec": round(max(0, age_seconds)),
        "bars": len(candles), "price": price, "atr_pct": round(atr, 4),
        "change_24h": change_24h, "change_7d": change_7d,
        "regime_7d": str(regimes(candles).iloc[-1]),
        "trend_monitor": {"name": "tsmom_168_720", "state": trend_state},
        "volume_24h_usd": row["volume_24h_usd"],
        "open_interest_usd": row["open_interest_usd"],
        "funding_hourly": row["funding"],
    }


def build_pack(*, state_file: str | Path = ROOT / "paper/state.json", top: int = 12,
               prefilter: int = 20, min_volume_usd: float = 1_000_000,
               min_oi_usd: float = 500_000, lookback_h: int = 800,
               min_enrichment_coverage: float = 0.90, expires_h: float = 2.0,
               weight_budget: int = HL_WEIGHT_BUDGET) -> dict:
    if not 1 <= top <= 12:
        raise ValueError("top deve essere tra 1 e 12")
    if not top <= prefilter <= 20:
        raise ValueError("prefilter deve essere tra top e 20")
    if lookback_h < 721:
        raise ValueError("lookback_h deve essere >= 721")
    if not 0 < min_enrichment_coverage <= 1:
        raise ValueError("min_enrichment_coverage deve essere in (0,1]")

    now = _now()
    census = perp_market_snapshot()
    if not census:
        raise RuntimeError("snapshot Hyperliquid vuoto")
    portfolio = _portfolio_snapshot(state_file)
    open_symbols = set(portfolio["open_symbols"])
    active = [row for row in census if not row["delisted"]]
    eligible = [
        row for row in active
        if row["dex"] == ""
        and row["mark"] > 0
        and row["volume_24h_usd"] >= min_volume_usd
        and row["open_interest_usd"] >= min_oi_usd
        and row["symbol"] not in open_symbols
    ]
    unique, duplicates_removed = _deduplicate(eligible)

    dex_count = len({row["dex"] for row in census})
    metadata_weight = HL_BASE_INFO_WEIGHT * (1 + dex_count)
    per_candle_weight = _candle_weight(lookback_h)
    budget_limit = max(0, (weight_budget - metadata_weight) // per_candle_weight)
    enrich_n = min(prefilter, budget_limit, len(unique))
    if len(unique) >= top and enrich_n < top:
        raise RuntimeError(
            f"budget HL insufficiente: arricchibili {enrich_n}, top richiesto {top}; "
            f"metadata_weight={metadata_weight}, candle_weight={per_candle_weight}")

    attempted = unique[:enrich_n]
    enriched, failures = [], []
    for row in attempted:
        try:
            enriched.append(_market_context(row, fetch_candles_cached(row["symbol"], lookback_h), now))
        except Exception as exc:
            failures.append({"symbol": row["symbol"], "reason": str(exc)[:240]})
    coverage = len(enriched) / len(attempted) if attempted else 1.0
    if coverage < min_enrichment_coverage:
        raise RuntimeError(
            f"coverage enrichment {coverage:.1%} < minimo {min_enrichment_coverage:.1%}: {failures}")

    research_markets = enriched[:top]
    for rank, row in enumerate(research_markets, 1):
        row["liquidity_rank"] = rank
    census_rows = sorted(census, key=lambda row: (row["dex"], row["symbol"]))
    pack = {
        "kind": PACK_KIND,
        "generated_at": _iso(now),
        "expires_at": _iso(now + timedelta(hours=expires_h)),
        "repo_commit": _repo_commit(),
        "model_target": "zai:glm-5.1",
        "universe": {
            "source": "Hyperliquid metaAndAssetCtxs, all perp dexs",
            "raw_symbols": len(census_rows),
            "active_symbols": len(active),
            "metadata_coverage": 1.0,
            "core_24x7_eligible": len(unique),
            "enrichment_attempted": len(attempted),
            "enriched": len(enriched),
            "enrichment_coverage": round(coverage, 6),
            "research_shortlist": len(research_markets),
            "census_sha256": content_hash(census_rows),
            "census": census_rows,
            "excluded_counts": {
                "delisted": sum(row["delisted"] for row in census),
                "below_volume": sum(not row["delisted"] and row["volume_24h_usd"] < min_volume_usd for row in census),
                "below_open_interest": sum(not row["delisted"] and row["open_interest_usd"] < min_oi_usd for row in census),
                "already_open": sum(row["symbol"] in open_symbols for row in census),
                "hip3_census_only": sum(not row["delisted"] and row["dex"] != "" for row in census),
                "duplicate_underlying": duplicates_removed,
                "enrichment_failed": len(failures),
            },
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
            "method": "all-dex metadata census -> core 24x7 volume/OI -> bounded candle context",
            "hip3_policy": "census_only_until_session_aware_gate_is_validated",
            "monitoring_only": True,
            "failures": failures,
        },
        "portfolio": portfolio,
        "research_markets": research_markets,
        "news": news_headlines(archive=False)[:20],
        "maker_contract": {
            "families_required": "5..8 distinct research families",
            "max_candidates": 1,
            "valid_outcomes": ["NO_CANDIDATE", "CANDIDATE"],
            "candidate_next_gate": "PREREG_REVIEW_ONLY",
            "inventory_first": True,
            "primary_sources_required": True,
        },
        "guardrails": GUARDRAILS,
    }
    return _with_pack_id(pack)


def render_prompt(pack: dict) -> str:
    verify_pack(pack)
    bounded = {
        "kind": pack["kind"], "pack_id": pack["pack_id"],
        "generated_at": pack["generated_at"], "expires_at": pack["expires_at"],
        "repo_commit": pack["repo_commit"],
        "universe_summary": {key: value for key, value in pack["universe"].items()
                             if key != "census"},
        "rate_limit_budget": pack["rate_limit_budget"],
        "selection": pack["selection"], "portfolio": pack["portfolio"],
        "research_markets": pack["research_markets"], "news": pack["news"],
        "maker_contract": pack["maker_contract"], "guardrails": pack["guardrails"],
    }
    return "# AlphaZero Labs — Daily Research Maker context\n\n" + _canonical_json(bounded)


def validate_maker(pack: dict, maker: dict, *, now: datetime | None = None) -> dict:
    verify_pack(pack)
    now = (now or _now()).astimezone(timezone.utc)
    maker = _expect_keys(maker, {
        "kind", "pack_id", "created_at", "maker_run_id", "model", "outcome",
        "inventory", "research_families", "candidate", "guardrails",
    }, "maker")
    if maker["kind"] != MAKER_KIND or maker["pack_id"] != pack["pack_id"]:
        raise ValueError("maker kind o pack_id non corrispondente")
    _text(maker["maker_run_id"], "maker.maker_run_id")
    if not _text(maker["model"], "maker.model").startswith(("gpt-5.6", "zai:")):
        raise ValueError("maker.model deve identificare GPT-5.6 oppure Z.AI")
    created = _parse_ts(maker["created_at"], "maker.created_at")
    generated = _parse_ts(pack["generated_at"], "pack.generated_at")
    expires = _parse_ts(pack["expires_at"], "pack.expires_at")
    if created < generated or created > expires:
        raise ValueError("maker.created_at deve cadere nella finestra valida del pack")
    if created > now + timedelta(minutes=5):
        raise ValueError("maker.created_at e' nel futuro")
    if now > expires + timedelta(minutes=5):
        raise ValueError("pack scaduto al momento della registrazione Maker")
    if maker["outcome"] not in ("NO_CANDIDATE", "CANDIDATE"):
        raise ValueError("maker.outcome invalido")
    if maker["guardrails"] != GUARDRAILS:
        raise ValueError("maker.guardrails deve confermare tutti i limiti L1")

    inventory = _expect_keys(maker["inventory"], {
        "note_path", "checked_at", "consumed_strategy_ids", "novelty_summary",
    }, "maker.inventory")
    _text(inventory["note_path"], "maker.inventory.note_path")
    checked = _parse_ts(inventory["checked_at"], "maker.inventory.checked_at")
    if checked < generated - timedelta(hours=24) or checked > created + timedelta(minutes=5):
        raise ValueError("inventory.checked_at non e' coerente col run Maker")
    _strings(inventory["consumed_strategy_ids"], "maker.inventory.consumed_strategy_ids")
    _text(inventory["novelty_summary"], "maker.inventory.novelty_summary")

    families = maker["research_families"]
    if not isinstance(families, list) or not 5 <= len(families) <= 8:
        raise ValueError("maker.research_families deve contenere 5..8 famiglie")
    ids, titles = set(), set()
    family_by_id = {}
    for index, family in enumerate(families):
        family = _expect_keys(family, {
            "family_id", "title", "hypothesis", "mechanism", "data_requirements",
            "source_urls", "novelty_status", "data_feasibility", "blockers",
        }, f"maker.research_families[{index}]")
        family_id = _text(family["family_id"], f"family[{index}].family_id")
        if not FAMILY_ID_RE.fullmatch(family_id) or family_id in ids:
            raise ValueError("family_id invalido o duplicato")
        title = _text(family["title"], f"family[{index}].title")
        if title.casefold() in titles:
            raise ValueError("titolo famiglia duplicato")
        ids.add(family_id); titles.add(title.casefold()); family_by_id[family_id] = family
        _text(family["hypothesis"], f"family[{index}].hypothesis")
        _text(family["mechanism"], f"family[{index}].mechanism")
        _strings(family["data_requirements"], f"family[{index}].data_requirements", allow_empty=False)
        urls = _strings(family["source_urls"], f"family[{index}].source_urls", allow_empty=False)
        if any(not url.startswith("https://") for url in urls):
            raise ValueError("source_urls deve contenere solo URL https")
        if family["novelty_status"] not in ("novel", "material_variant", "consumed"):
            raise ValueError("novelty_status invalido")
        if family["data_feasibility"] not in ("feasible", "blocked"):
            raise ValueError("data_feasibility invalido")
        blockers = _strings(family["blockers"], f"family[{index}].blockers")
        if (family["data_feasibility"] == "blocked") != bool(blockers):
            raise ValueError("blockers deve spiegare esattamente una data_feasibility blocked")

    candidate = maker["candidate"]
    if maker["outcome"] == "NO_CANDIDATE":
        if candidate is not None:
            raise ValueError("NO_CANDIDATE richiede candidate=null")
    else:
        candidate = _expect_keys(candidate, {
            "family_id", "thesis", "prereg_scope", "data_contract", "falsification", "next_gate",
        }, "maker.candidate")
        family_id = _text(candidate["family_id"], "maker.candidate.family_id")
        if family_id not in family_by_id:
            raise ValueError("candidate.family_id non appartiene alle famiglie")
        selected = family_by_id[family_id]
        if selected["novelty_status"] == "consumed" or selected["data_feasibility"] != "feasible":
            raise ValueError("la famiglia candidata non supera novelty e data feasibility")
        if selected["blockers"]:
            raise ValueError("la famiglia candidata non puo avere blocker")
        for field in ("thesis", "prereg_scope", "falsification"):
            _text(candidate[field], f"maker.candidate.{field}")
        _strings(candidate["data_contract"], "maker.candidate.data_contract", allow_empty=False)
        if candidate["next_gate"] != "PREREG_REVIEW_ONLY":
            raise ValueError("candidate.next_gate deve essere PREREG_REVIEW_ONLY")
    return {"valid": True, "outcome": maker["outcome"], "maker_sha256": content_hash(maker)}


def validate_checker(pack: dict, maker: dict, checker: dict,
                     *, now: datetime | None = None) -> dict:
    now = (now or _now()).astimezone(timezone.utc)
    verify_pack(pack)
    checker = _expect_keys(checker, {
        "kind", "pack_id", "maker_sha256", "maker_run_id", "checked_at",
        "checker_run_id", "verdict", "blockers", "notes", "checks",
    }, "checker")
    if checker["kind"] != CHECKER_KIND or checker["pack_id"] != pack["pack_id"]:
        raise ValueError("checker kind o pack_id non corrispondente")
    if checker["maker_sha256"] != content_hash(maker):
        raise ValueError("checker.maker_sha256 non corrisponde: maker alterato")
    maker_result = validate_maker(pack, maker, now=now)
    maker_run_id = _text(checker["maker_run_id"], "checker.maker_run_id")
    checker_run_id = _text(checker["checker_run_id"], "checker.checker_run_id")
    if maker_run_id != maker["maker_run_id"] or checker_run_id == maker_run_id:
        raise ValueError("Maker e Checker devono avere identita distinte")
    checked = _parse_ts(checker["checked_at"], "checker.checked_at")
    if checked < _parse_ts(maker["created_at"], "maker.created_at"):
        raise ValueError("checker.checked_at precede il Maker")
    if checked > _parse_ts(pack["expires_at"], "pack.expires_at"):
        raise ValueError("checker.checked_at supera la scadenza del pack")
    if checked > now + timedelta(minutes=5):
        raise ValueError("checker.checked_at e' nel futuro")
    if now > _parse_ts(pack["expires_at"], "pack.expires_at") + timedelta(minutes=5):
        raise ValueError("pack scaduto al momento della registrazione Checker")
    if checker["verdict"] not in APPROVE_VERDICTS | {"REJECT"}:
        raise ValueError("checker.verdict invalido")
    blockers = _strings(checker["blockers"], "checker.blockers")
    _text(checker["notes"], "checker.notes")
    checks = _expect_keys(checker["checks"], CHECKS, "checker.checks")
    if any(type(value) is not bool for value in checks.values()):
        raise ValueError("checker.checks deve contenere booleani")
    expected = ("APPROVE_NO_CANDIDATE" if maker["outcome"] == "NO_CANDIDATE"
                else "APPROVE_PREREG_ONLY")
    if checker["verdict"] in APPROVE_VERDICTS:
        if checker["verdict"] != expected or blockers or not all(checks.values()):
            raise ValueError("receipt APPROVE incoerente con outcome, blocker o checks")
    elif not blockers:
        raise ValueError("REJECT richiede almeno un blocker")
    return {"valid": True, "verdict": checker["verdict"],
            "maker_sha256": maker_result["maker_sha256"]}


def _read_json(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: atteso oggetto JSON")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack_cmd = commands.add_parser("pack")
    pack_cmd.add_argument("--out", required=True)
    pack_cmd.add_argument("--state-file", default=str(ROOT / "paper/state.json"))
    pack_cmd.add_argument("--top", type=int, default=12)
    pack_cmd.add_argument("--prefilter", type=int, default=20)
    prompt_cmd = commands.add_parser("prompt")
    prompt_cmd.add_argument("--pack", required=True)
    maker_cmd = commands.add_parser("validate-maker")
    maker_cmd.add_argument("--pack", required=True); maker_cmd.add_argument("--maker", required=True)
    checker_cmd = commands.add_parser("validate-checker")
    checker_cmd.add_argument("--pack", required=True); checker_cmd.add_argument("--maker", required=True)
    checker_cmd.add_argument("--checker", required=True)
    args = parser.parse_args()

    if args.command == "pack":
        value = build_pack(state_file=args.state_file, top=args.top, prefilter=args.prefilter)
        atomic_write_text(args.out, json.dumps(value, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({"pack_id": value["pack_id"], "path": str(Path(args.out).resolve()),
                          "raw_symbols": value["universe"]["raw_symbols"],
                          "research_shortlist": value["universe"]["research_shortlist"]}))
    elif args.command == "prompt":
        print(render_prompt(_read_json(args.pack)))
    elif args.command == "validate-maker":
        print(json.dumps(validate_maker(_read_json(args.pack), _read_json(args.maker))))
    else:
        print(json.dumps(validate_checker(_read_json(args.pack), _read_json(args.maker),
                                          _read_json(args.checker))))


if __name__ == "__main__":
    main()
