import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import agents_paper, codex_desk


NOW = datetime(2026, 7, 13, 1, 0, tzinfo=timezone.utc)


def _candidate(symbol="BTC", direction="long", rank=1):
    return {
        "rank": rank, "symbol": symbol, "dex": "", "direction_from_gate": direction,
        "gate": {"name": "tsmom_168_720", "value": 1 if direction == "long" else -1, "passed": True},
        "asof": (NOW - timedelta(hours=1)).isoformat(), "data_age_sec": 3600,
        "bars": 801, "price": 100.0, "atr_pct": 1.0,
        "change_24h": 0.02, "change_7d": 0.08, "regime_7d": "bull",
        "volume_24h_usd": 20_000_000.0, "open_interest_usd": 10_000_000.0,
        "funding_hourly": 0.00001, "funding_apr": 0.0876,
        "max_exchange_leverage": 50, "trade_eligible": True,
        "eligibility_reasons": ["liquidity", "fresh_721h_history", "tsmom_direction_frozen"],
    }


def _pack(candidates=None, expires=None):
    candidates = candidates if candidates is not None else [_candidate()]
    payload = {
        "kind": codex_desk.PACK_KIND,
        "generated_at": NOW.isoformat(),
        "expires_at": (expires or NOW + timedelta(hours=2)).isoformat(),
        "repo_commit": "a" * 40, "prompt_version": 2, "model_target": "gpt-5.6",
        "universe": {"census": [], "census_sha256": codex_desk.content_hash([])},
        "portfolio": {"account": "agents-v1", "equity": 10_000,
                      "open_position_count": 0, "open_positions": []},
        "constraints": {}, "candidates": candidates, "news": [], "lessons": [], "task": {},
    }
    return codex_desk._with_pack_id(payload)


def _decision(pack, **proposal_overrides):
    proposal = {
        "action": "trade", "symbol": "BTC", "direction": "long", "leverage": 1.5,
        "risk_pct": 0.8, "stop_pct": 1.5, "target_r": 2.0, "time_stop_h": 72,
        "thesis": "TSMOM persistente con rischio limitato",
        "invalidation": "chiusura oraria oltre lo stop",
    }
    proposal.update(proposal_overrides)
    return {
        "kind": codex_desk.DECISION_KIND, "pack_id": pack["pack_id"],
        "created_at": (NOW + timedelta(minutes=5)).isoformat(), "model": "gpt-5.6-terra",
        "proposal": proposal,
        "risk": {"verdict": "approve", "size_multiplier": 1.0, "notes": "book compatibile"},
        "judgment": {"selected_rank": 1, "risks": [], "rejected_candidates": [],
                     "lessons_applied": []},
    }


def _approval(pack, decision, verdict="APPROVE"):
    return {
        "kind": codex_desk.APPROVAL_KIND, "pack_id": pack["pack_id"],
        "decision_sha256": codex_desk.content_hash(decision), "verdict": verdict,
        "checked_at": (NOW + timedelta(minutes=10)).isoformat(),
        "checker_run_id": "checker-independent-1", "notes": "all checks passed",
    }


def _market_row(symbol, volume, *, dex="", delisted=False, oi=5_000_000):
    return {
        "symbol": symbol, "dex": dex, "delisted": delisted, "mark": 100.0,
        "prev_day_px": 99.0, "change_24h": 0.01, "volume_24h_usd": float(volume),
        "open_interest_usd": float(oi), "funding": 0.00001, "max_leverage": 20.0,
    }


def _live(symbol, direction):
    ts = pd.date_range(end=NOW - timedelta(hours=1), periods=802, freq="h", tz="UTC")
    if direction > 0:
        close = np.linspace(50, 100, len(ts))
    elif direction < 0:
        close = np.linspace(100, 50, len(ts))
    else:
        close = np.full(len(ts), 100.0)
    candles = pd.DataFrame({"ts": ts, "open": close, "high": close * 1.01,
                            "low": close * 0.99, "close": close,
                            "volume": np.full(len(ts), 1000.0)})
    return {"symbol": symbol, "candles": candles, "forming": candles.iloc[-1],
            "flow": None, "funding": None}


def test_all_symbol_pack_keeps_full_census_but_bounds_model_shortlist(monkeypatch):
    rows = [
        _market_row("BTC", 30_000_000), _market_row("ETH", 20_000_000),
        _market_row("SOL", 10_000_000), _market_row("xyz:BTC", 5_000_000, dex="xyz"),
        _market_row("OLD", 50_000_000, delisted=True),
    ]
    directions = {"BTC": 1, "ETH": -1, "SOL": 0}
    monkeypatch.setattr(codex_desk, "perp_market_snapshot", lambda: rows)
    monkeypatch.setattr(codex_desk, "fetch_live_cached",
                        lambda symbol, *_args, **_kwargs: _live(symbol, directions[symbol]))
    monkeypatch.setattr(codex_desk, "news_headlines", lambda **_kwargs: [])
    monkeypatch.setattr(codex_desk, "recall_lessons", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(codex_desk, "_repo_commit", lambda: "b" * 40)
    monkeypatch.setattr(codex_desk, "_now", lambda: NOW)

    pack = codex_desk.build_pack(top=2, prefilter=3, weight_budget=1000)

    assert pack["universe"]["raw_symbols"] == 5
    assert pack["universe"]["metadata_coverage"] == 1.0
    assert [c["symbol"] for c in pack["candidates"]] == ["BTC", "ETH"]
    assert pack["universe"]["excluded_counts"]["duplicate_underlying"] == 0
    assert pack["universe"]["excluded_counts"]["hip3_gate_not_validated"] == 1
    prompt = codex_desk.render_prompt(pack)
    assert "OLD" not in prompt
    assert len(prompt) < len(json.dumps(pack))
    codex_desk.verify_pack(pack)


def test_pack_hash_detects_tampering():
    pack = _pack()
    pack["candidates"][0]["price"] = 999
    with pytest.raises(ValueError, match="alterato"):
        codex_desk.verify_pack(pack)


def test_decision_rejects_outside_shortlist_direction_and_expiry():
    pack = _pack()
    with pytest.raises(ValueError, match="shortlist"):
        codex_desk.validate_decision(pack, _decision(pack, symbol="SOL"), now=NOW + timedelta(minutes=10))
    with pytest.raises(ValueError, match="direction"):
        codex_desk.validate_decision(pack, _decision(pack, direction="short"), now=NOW + timedelta(minutes=10))
    expired = _pack(expires=NOW + timedelta(minutes=1))
    with pytest.raises(ValueError, match="scaduto"):
        codex_desk.validate_decision(expired, _decision(expired), now=NOW + timedelta(minutes=2))


def test_decision_enforces_hard_limits_and_atr(monkeypatch):
    monkeypatch.setenv("HARD_LIMITS_BYPASS", "1")  # nuovo path deve ignorare il bypass storico
    pack = _pack()
    with pytest.raises(ValueError, match="hard limits"):
        codex_desk.validate_decision(pack, _decision(pack, leverage=3.0), now=NOW + timedelta(minutes=10))
    with pytest.raises(ValueError, match="hard limits"):
        codex_desk.validate_decision(pack, _decision(pack, stop_pct=0.8), now=NOW + timedelta(minutes=10))


def test_no_trade_contract_is_valid():
    pack = _pack([])
    decision = _decision(pack, action="no_trade", thesis="nessun setup supera il gate")
    decision["proposal"] = {"action": "no_trade", "thesis": "nessun setup supera il gate"}
    decision["risk"] = {"verdict": "veto", "size_multiplier": 0.0, "notes": "shortlist vuota"}
    decision["judgment"]["selected_rank"] = None
    receipt = codex_desk.validate_decision(pack, decision, now=NOW + timedelta(minutes=10))
    assert receipt["valid"] and not receipt["executable"]


def test_approval_hash_and_verdict_are_fail_closed():
    pack = _pack()
    decision = _decision(pack)
    approval = _approval(pack, decision)
    assert codex_desk.validate_approval(pack, decision, approval,
                                        now=NOW + timedelta(minutes=10))["executable"]
    bad = {**approval, "decision_sha256": "0" * 64}
    with pytest.raises(ValueError, match="decision_sha256"):
        codex_desk.validate_approval(pack, decision, bad, now=NOW + timedelta(minutes=10))
    with pytest.raises(ValueError, match="APPROVE"):
        codex_desk.validate_approval(pack, decision, _approval(pack, decision, "REJECT"),
                                     now=NOW + timedelta(minutes=10))
    future = {**approval, "checked_at": (NOW + timedelta(minutes=30)).isoformat()}
    with pytest.raises(ValueError, match="futuro"):
        codex_desk.validate_approval(pack, decision, future,
                                     now=NOW + timedelta(minutes=10))


def test_ingest_requires_approval_and_is_idempotent(monkeypatch, tmp_path):
    path = tmp_path / "decisions.jsonl"
    pack, decision = _pack(), None
    decision = _decision(pack)
    approval = _approval(pack, decision)
    monkeypatch.setattr(codex_desk, "DECISIONS", path)
    monkeypatch.setattr(codex_desk, "_now", lambda: NOW + timedelta(minutes=10))

    first = codex_desk.ingest(pack, decision, approval)
    second = codex_desk.ingest(pack, decision, approval)

    assert first["ingested"] is True
    assert second == {**first, "ingested": False, "reason": "duplicate"}
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["stage"] == "final"
    assert rows[0]["admission"]["status"] == "approved"


def test_executor_only_consumes_admitted_non_veto_decisions(monkeypatch, tmp_path):
    base = {
        "stage": "final", "strategy": "agents-v1", "logged_at": "2026-07-13T01:00:00+00:00",
        "proposal": {"action": "trade", "symbol": "BTC"},
        "admission": {"status": "approved", "executable": True,
                      "expires_at": "2099-01-01T00:00:00+00:00"},
        "provenance": {"pack_id": "p", "decision_sha256": "d", "checker_run_id": "c"},
    }
    rows = [
        {**base, "risk": {"verdict": "approve", "size_multiplier": 1.0}},
        {**base, "logged_at": "2026-07-13T01:01:00+00:00",
         "risk": {"verdict": "veto", "size_multiplier": 0.0}},
        {**base, "logged_at": "2026-07-13T01:02:00+00:00", "admission": {},
         "risk": {"verdict": "approve", "size_multiplier": 1.0}},
    ]
    path = tmp_path / "decisions.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    monkeypatch.setattr(agents_paper, "DECISIONS", path)
    monkeypatch.setattr(agents_paper, "SOURCE", "agents-v1")
    assert agents_paper.pending_decisions("") == [rows[0]]


def test_executor_rejects_direct_call_without_admission(monkeypatch):
    events = []
    monkeypatch.setattr(agents_paper, "log_event", events.append)
    result = agents_paper.open_from_decision({"proposal": {"symbol": "BTC"}}, 10_000)
    assert result is None
    assert "admission" in events[0]["reason"]
