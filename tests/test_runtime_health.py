import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.runtime_health import (build_manifest, load_coverage, load_health,
                                    validate_manifest, write_coverage)


NOW = datetime(2026, 7, 13, 12, tzinfo=timezone.utc)


def test_all_critical_success_is_publishable():
    health = build_manifest(["paper=success", "exits=success"], ["propr=skipped"],
                            run_id="42-1", commit="abc", now=NOW)
    assert health["status"] == "healthy"
    assert health["publish_allowed"] is True
    assert validate_manifest(health, now=NOW) == (True, [])


def test_critical_failure_blocks_publish():
    health = build_manifest(["paper=failure", "exits=success"], [],
                            run_id="42-1", commit="abc", now=NOW)
    assert health["status"] == "critical"
    assert health["publish_allowed"] is False
    ok, reasons = validate_manifest(health, now=NOW)
    assert ok is False
    assert "health_critical_check_failed" in reasons


def test_optional_failure_is_visible_but_publishable():
    health = build_manifest(["paper=success"], ["cot=failure"],
                            run_id="42-1", commit="abc", now=NOW)
    assert health["status"] == "degraded"
    assert health["warnings"] == ["cot"]
    assert health["publish_allowed"] is True


def test_missing_invalid_and_stale_health_fail_closed(tmp_path):
    missing = load_health(tmp_path / "missing.json", now=NOW)
    assert missing["publish_allowed"] is False
    assert missing["validation_reasons"] == ["health_missing"]
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert load_health(bad, now=NOW)["validation_reasons"] == ["health_invalid_json"]
    stale = build_manifest(["paper=success"], [], run_id="1", commit="a",
                           now=NOW - timedelta(hours=3))
    bad.write_text(json.dumps(stale))
    assert "health_stale" in load_health(bad, now=NOW)["validation_reasons"]


def test_malformed_check_schema_is_blocked():
    health = build_manifest(["paper=success"], [], run_id="1", commit="a", now=NOW)
    health["checks"] = [{"name": "paper", "critical": "yes", "outcome": "success"}]
    ok, reasons = validate_manifest(health, now=NOW)
    assert ok is False
    assert "health_checks_invalid" in reasons


def test_exact_ticker_coverage_is_embedded_and_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_RUN_ID", "42-1")
    record = write_coverage("alpha-v1", ["BTC", "ETH", "SOL"], ["BTC", "ETH"],
                            output_dir=tmp_path)
    health = build_manifest(["paper=success"], [], run_id="42-1", commit="abc", now=NOW,
                            coverage=load_coverage("42-1", tmp_path))
    assert record["expected_count"] == 3
    assert record["observed_count"] == 2
    assert record["missing"] == ["SOL"]
    assert health["publish_allowed"] is False
    assert health["errors"] == ["coverage:alpha-v1"]


def test_required_coverage_record_cannot_disappear_silently():
    health = build_manifest(["paper=success"], [], run_id="42-1", commit="abc", now=NOW,
                            coverage=[], required_coverage=["paper-all"])
    assert health["publish_allowed"] is False
    assert health["errors"] == ["coverage:paper-all"]
    ok, reasons = validate_manifest(health, now=NOW)
    assert ok is False
    assert "health_required_coverage_missing" in reasons
