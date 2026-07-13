import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import research_ops as ops
from scripts import research_pack as rp


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


def _pack(sequence=1):
    census = [{
        "symbol": "BTC", "dex": "", "delisted": False, "mark": 100.0,
        "prev_day_px": 99.0, "change_24h": 0.01, "volume_24h_usd": 1_000_000,
        "open_interest_usd": 500_000, "funding": 0.0, "max_leverage": 5.0,
    }]
    return rp._with_pack_id({
        "kind": rp.PACK_KIND, "generated_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
        "test_sequence": sequence,
        "universe": {"census": census, "census_sha256": rp.content_hash(census)},
    })


def _maker(pack):
    return {
        "kind": rp.MAKER_KIND, "pack_id": pack["pack_id"],
        "created_at": (NOW + timedelta(minutes=10)).isoformat(),
        "maker_run_id": "maker-1", "model": "gpt-5.6-sol", "outcome": "NO_CANDIDATE",
        "inventory": {
            "note_path": "wiki/Registry Segnali.md", "checked_at": NOW.isoformat(),
            "consumed_strategy_ids": [], "novelty_summary": "Inventory checked",
        },
        "research_families": [{
            "family_id": f"family-{index}", "title": f"Family {index}",
            "hypothesis": "Testable", "mechanism": "Structural",
            "data_requirements": ["PIT data"],
            "source_urls": [f"https://example.org/{index}"],
            "novelty_status": "novel", "data_feasibility": "feasible", "blockers": [],
        } for index in range(1, 6)],
        "candidate": None, "guardrails": dict(rp.GUARDRAILS),
    }


def _checker(pack, maker):
    return {
        "kind": rp.CHECKER_KIND, "pack_id": pack["pack_id"],
        "maker_sha256": rp.content_hash(maker), "maker_run_id": maker["maker_run_id"],
        "checked_at": (NOW + timedelta(minutes=20)).isoformat(),
        "checker_run_id": "checker-2", "verdict": "APPROVE_NO_CANDIDATE",
        "blockers": [], "notes": "Independent review passed",
        "checks": {key: True for key in rp.CHECKS},
    }


def _fixture(tmp_path):
    root = tmp_path / "ops"; root.mkdir()
    (root / "STATE.json").write_text(json.dumps(ops.initial_state(started_at=NOW, status="active")))
    (root / "RUN_LOG.jsonl").write_text("")
    pack = _pack(); maker = _maker(pack); checker = _checker(pack, maker)
    run = root / "runs" / pack["pack_id"]; run.mkdir(parents=True)
    paths = []
    for name, value in (("pack.json", pack), ("maker.json", maker), ("checker.json", checker)):
        path = run / name; path.write_text(json.dumps(value)); paths.append(path)
    return root, pack, maker, checker, paths


def test_state_machine_enforces_backpressure_and_independent_receipt(tmp_path, monkeypatch):
    root, pack, _maker_value, _checker_value, (pack_path, maker_path, checker_path) = _fixture(tmp_path)
    monkeypatch.setattr(ops, "_now", lambda: NOW + timedelta(minutes=30))
    result = ops.record_maker(root, pack_path, maker_path)
    assert result["outcome"] == "NO_CANDIDATE"
    assert ops.status(root)["work_pending"] is True
    with pytest.raises(ValueError, match="backpressure"):
        ops.record_maker(root, pack_path, maker_path)
    checked = ops.record_checker(root, pack_path, maker_path, checker_path)
    assert checked["verdict"] == "APPROVE_NO_CANDIDATE"
    assert checked["clean_streak_days"] == 1
    current = ops.status(root)
    assert current["work_pending"] is False
    assert current["counters"] == {
        "maker_runs": 1, "checker_runs": 1, "candidate": 0,
        "no_candidate": 1, "rejected": 0,
    }
    events = [json.loads(line) for line in (root / "RUN_LOG.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events] == ["maker_recorded", "checker_recorded"]
    assert pack_path.stat().st_mode & 0o222 == 0


def test_state_machine_rejects_artifacts_outside_ops_runs(tmp_path):
    root, _pack_value, _maker_value, _checker_value, (pack_path, _maker_path, _checker_path) = _fixture(tmp_path)
    outside = tmp_path / "maker.json"; outside.write_text("{}")
    with pytest.raises(ValueError, match="fuori"):
        ops.record_maker(root, pack_path, outside)


def test_kill_switch_blocks_maker_and_checker_mutations(tmp_path, monkeypatch):
    root, _pack_value, _maker_value, _checker_value, paths = _fixture(tmp_path)
    pack_path, maker_path, checker_path = paths
    monkeypatch.setattr(ops, "_now", lambda: NOW + timedelta(minutes=30))
    ops.record_maker(root, pack_path, maker_path)
    state = json.loads((root / "STATE.json").read_text())
    state["status"] = "paused"
    (root / "STATE.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="paused"):
        ops.record_checker(root, pack_path, maker_path, checker_path)


def test_daily_budget_rejects_second_completed_maker_same_rome_date(tmp_path, monkeypatch):
    root, _pack_value, _maker_value, _checker_value, paths = _fixture(tmp_path)
    pack_path, maker_path, checker_path = paths
    monkeypatch.setattr(ops, "_now", lambda: NOW + timedelta(minutes=30))
    ops.record_maker(root, pack_path, maker_path)
    ops.record_checker(root, pack_path, maker_path, checker_path)

    second_pack = _pack(sequence=2); second_maker = _maker(second_pack)
    second_maker["maker_run_id"] = "maker-3"
    run = root / "runs" / second_pack["pack_id"]; run.mkdir()
    second_pack_path = run / "pack.json"; second_maker_path = run / "maker.json"
    second_pack_path.write_text(json.dumps(second_pack)); second_maker_path.write_text(json.dumps(second_maker))
    with pytest.raises(ValueError, match="esiste gia un Maker utile"):
        ops.record_maker(root, second_pack_path, second_maker_path)
    assert ops.status(root)["counters"]["maker_runs"] == 1


def test_future_checker_cannot_advance_observation(tmp_path, monkeypatch):
    root, _pack_value, _maker_value, _checker_value, paths = _fixture(tmp_path)
    pack_path, maker_path, checker_path = paths
    monkeypatch.setattr(ops, "_now", lambda: NOW + timedelta(minutes=30))
    ops.record_maker(root, pack_path, maker_path)
    checker = json.loads(checker_path.read_text())
    checker["checked_at"] = (NOW + timedelta(days=30)).isoformat()
    checker_path.write_text(json.dumps(checker))
    with pytest.raises(ValueError, match="scadenza"):
        ops.record_checker(root, pack_path, maker_path, checker_path)
    current = ops.status(root)
    assert current["work_pending"] is True
    assert current["observation"]["clean_streak_days"] == 0
