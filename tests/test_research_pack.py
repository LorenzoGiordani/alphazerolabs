import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import live
from scripts import research_pack as rp


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


def _row(symbol, *, dex="", volume=10_000_000, oi=2_000_000, delisted=False):
    return {
        "symbol": symbol, "dex": dex, "delisted": delisted,
        "mark": 100.0, "prev_day_px": 99.0, "change_24h": 1 / 99,
        "volume_24h_usd": volume, "open_interest_usd": oi,
        "funding": 0.00001, "max_leverage": 10.0,
    }


def _candles():
    count = 800
    ts = pd.date_range(NOW - timedelta(hours=count), periods=count, freq="h", tz="UTC")
    close = pd.Series([100 + index * 0.1 for index in range(count)])
    return {"candles": pd.DataFrame({
        "ts": ts, "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": 1000.0,
    }), "forming": None, "flow": None, "funding": None}


def _patch_pack(monkeypatch, census, *, fetch=None):
    monkeypatch.setattr(rp, "_now", lambda: NOW)
    monkeypatch.setattr(rp, "_repo_commit", lambda: "abc123")
    monkeypatch.setattr(rp, "perp_market_snapshot", lambda: census)
    monkeypatch.setattr(rp, "fetch_candles_cached", fetch or (lambda *_args: _candles()))
    monkeypatch.setattr(rp, "news_headlines", lambda *args, **kwargs: [])


def _maker(pack, outcome="NO_CANDIDATE"):
    families = [{
        "family_id": f"family-{index}", "title": f"Family {index}",
        "hypothesis": "Falsifiable hypothesis", "mechanism": "Structural mechanism",
        "data_requirements": ["hourly price and volume"],
        "source_urls": [f"https://example.org/source/{index}"],
        "novelty_status": "novel", "data_feasibility": "feasible", "blockers": [],
    } for index in range(1, 6)]
    candidate = None
    if outcome == "CANDIDATE":
        candidate = {
            "family_id": "family-1", "thesis": "Testable prereg thesis",
            "prereg_scope": "Core crypto universe only",
            "data_contract": ["point-in-time hourly candles"],
            "falsification": "Reject if the preregistered metric misses its floor",
            "next_gate": "PREREG_REVIEW_ONLY",
        }
    return {
        "kind": rp.MAKER_KIND, "pack_id": pack["pack_id"],
        "created_at": (NOW + timedelta(minutes=20)).isoformat(),
        "maker_run_id": "maker-run-1", "model": "gpt-5.6-sol", "outcome": outcome,
        "inventory": {
            "note_path": "wiki/Consumed Strategy Inventory.md",
            "checked_at": (NOW + timedelta(minutes=5)).isoformat(),
            "consumed_strategy_ids": ["existing-1"], "novelty_summary": "Compared all five families",
        },
        "research_families": families, "candidate": candidate,
        "guardrails": dict(rp.GUARDRAILS),
    }


def _checker(pack, maker, verdict):
    return {
        "kind": rp.CHECKER_KIND, "pack_id": pack["pack_id"],
        "maker_sha256": rp.content_hash(maker), "maker_run_id": maker["maker_run_id"],
        "checked_at": (NOW + timedelta(minutes=30)).isoformat(),
        "checker_run_id": "checker-run-2", "verdict": verdict,
        "blockers": [], "notes": "Independent contract and source review passed",
        "checks": {key: True for key in rp.CHECKS},
    }


def test_strict_market_snapshot_covers_core_and_hip3(monkeypatch):
    monkeypatch.setattr(live, "_perp_dexs", lambda: ["", "xyz"])

    def post(payload, **_kwargs):
        dex = payload["dex"]
        return [{"universe": [{"name": "BTC" if not dex else "GOLD", "maxLeverage": 5}]},
                [{"markPx": "100", "prevDayPx": "99", "dayNtlVlm": "20",
                  "openInterest": "3", "funding": "0"}]]

    monkeypatch.setattr(live, "_hl_post", post)
    rows = live.perp_market_snapshot()
    assert [row["symbol"] for row in rows] == ["BTC", "xyz:GOLD"]
    assert rows[1]["open_interest_usd"] == 300


def test_strict_market_snapshot_rejects_partial_context(monkeypatch):
    monkeypatch.setattr(live, "_perp_dexs", lambda: [""])
    monkeypatch.setattr(live, "_hl_post", lambda *_args, **_kwargs: [
        {"universe": [{"name": "BTC", "maxLeverage": 5}]}, []])
    with pytest.raises(RuntimeError, match="universe/context mismatch"):
        live.perp_market_snapshot()


def test_pack_census_is_all_dex_but_candles_are_bounded_core_only(tmp_path, monkeypatch):
    census = [_row(f"COIN{index}") for index in range(13)] + [_row("xyz:GOLD", dex="xyz")]
    calls = []

    def fetch(symbol, lookback):
        calls.append((symbol, lookback)); return _candles()

    _patch_pack(monkeypatch, census, fetch=fetch)
    state = tmp_path / "state.json"; state.write_text("{}")
    pack = rp.build_pack(state_file=state)
    rp.verify_pack(pack)
    assert pack["universe"]["raw_symbols"] == 14
    assert pack["universe"]["excluded_counts"]["hip3_census_only"] == 1
    assert len(calls) == 13 and all(not symbol.startswith("xyz:") for symbol, _ in calls)
    assert len(pack["research_markets"]) == 12
    assert pack["selection"]["monitoring_only"] is True
    assert pack["portfolio"]["source_sha256"] == rp.content_hash({})


def test_pack_fails_closed_below_enrichment_coverage(tmp_path, monkeypatch):
    census = [_row(f"COIN{index}") for index in range(10)]

    def fetch(symbol, _lookback):
        if symbol in {"COIN0", "COIN1"}:
            raise RuntimeError("unavailable")
        return _candles()

    _patch_pack(monkeypatch, census, fetch=fetch)
    state = tmp_path / "state.json"; state.write_text("{}")
    with pytest.raises(RuntimeError, match="coverage enrichment 80.0%"):
        rp.build_pack(state_file=state, top=5, prefilter=10)


def test_pack_tampering_and_contract_scope_fail_closed(tmp_path, monkeypatch):
    _patch_pack(monkeypatch, [_row(f"COIN{index}") for index in range(5)])
    state = tmp_path / "state.json"; state.write_text("{}")
    journal = tmp_path / "decisions.jsonl"; journal.write_text("immutable\n")
    before = (state.read_bytes(), journal.read_bytes())
    pack = rp.build_pack(state_file=state, top=5, prefilter=5)
    tampered = copy.deepcopy(pack); tampered["universe"]["active_symbols"] = 999
    with pytest.raises(ValueError, match="pack alterato"):
        rp.verify_pack(tampered)
    maker = _maker(pack)
    assert rp.validate_maker(pack, maker, now=NOW + timedelta(minutes=20))["valid"] is True
    out_of_scope = copy.deepcopy(maker); out_of_scope["backtest_sharpe"] = 3.1
    with pytest.raises(ValueError, match="extra=.*backtest_sharpe"):
        rp.validate_maker(pack, out_of_scope)
    assert (state.read_bytes(), journal.read_bytes()) == before


@pytest.mark.parametrize("outcome,verdict", [
    ("NO_CANDIDATE", "APPROVE_NO_CANDIDATE"),
    ("CANDIDATE", "APPROVE_PREREG_ONLY"),
])
def test_checker_exact_hash_distinct_identity_and_bounded_verdict(tmp_path, monkeypatch,
                                                                 outcome, verdict):
    _patch_pack(monkeypatch, [_row(f"COIN{index}") for index in range(5)])
    state = tmp_path / "state.json"; state.write_text("{}")
    pack = rp.build_pack(state_file=state, top=5, prefilter=5)
    maker = _maker(pack, outcome)
    checker = _checker(pack, maker, verdict)
    assert rp.validate_checker(pack, maker, checker,
                               now=NOW + timedelta(minutes=30))["verdict"] == verdict
    checker["checker_run_id"] = maker["maker_run_id"]
    with pytest.raises(ValueError, match="identita distinte"):
        rp.validate_checker(pack, maker, checker, now=NOW + timedelta(minutes=30))


def test_checker_rejects_maker_tampering(tmp_path, monkeypatch):
    _patch_pack(monkeypatch, [_row(f"COIN{index}") for index in range(5)])
    state = tmp_path / "state.json"; state.write_text("{}")
    pack = rp.build_pack(state_file=state, top=5, prefilter=5)
    maker = _maker(pack)
    checker = _checker(pack, maker, "APPROVE_NO_CANDIDATE")
    maker["inventory"]["novelty_summary"] = "changed after review"
    with pytest.raises(ValueError, match="maker alterato"):
        rp.validate_checker(pack, maker, checker)


def test_checker_rejects_expired_or_future_receipt(tmp_path, monkeypatch):
    _patch_pack(monkeypatch, [_row(f"COIN{index}") for index in range(5)])
    state = tmp_path / "state.json"; state.write_text("{}")
    pack = rp.build_pack(state_file=state, top=5, prefilter=5)
    maker = _maker(pack)
    checker = _checker(pack, maker, "APPROVE_NO_CANDIDATE")
    checker["checked_at"] = (NOW + timedelta(hours=2, minutes=1)).isoformat()
    with pytest.raises(ValueError, match="scadenza"):
        rp.validate_checker(pack, maker, checker, now=NOW + timedelta(hours=2, minutes=1))
    checker["checked_at"] = (NOW + timedelta(minutes=30)).isoformat()
    with pytest.raises(ValueError, match="futuro"):
        rp.validate_checker(pack, maker, checker, now=NOW + timedelta(minutes=20))


def test_expired_pack_cannot_be_registered_later(tmp_path, monkeypatch):
    _patch_pack(monkeypatch, [_row(f"COIN{index}") for index in range(5)])
    state = tmp_path / "state.json"; state.write_text("{}")
    pack = rp.build_pack(state_file=state, top=5, prefilter=5)
    maker = _maker(pack)
    checker = _checker(pack, maker, "APPROVE_NO_CANDIDATE")
    late = NOW + timedelta(days=30)
    with pytest.raises(ValueError, match="scaduto"):
        rp.validate_maker(pack, maker, now=late)
    with pytest.raises(ValueError, match="scaduto"):
        rp.validate_checker(pack, maker, checker, now=late)
