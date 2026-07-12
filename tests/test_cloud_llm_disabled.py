import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_scheduled_runtime_has_no_llm_calls_or_credentials():
    workflow = (ROOT / ".github/workflows/paper-run.yml").read_text()
    exits = (ROOT / ".github/workflows/paper-exits.yml").read_text()
    deploy = (ROOT / ".github/workflows/deploy-dashboard.yml").read_text()
    cron = (ROOT / "scripts/cron_run.sh").read_text()

    assert 'LLM_RUNTIME_DISABLED: "1"' in workflow
    assert 'LLM_RUNTIME_DISABLED: "1"' in exits
    assert 'LLM_RUNTIME_DISABLED: "1"' in deploy
    assert "export LLM_RUNTIME_DISABLED=1" in cron

    for forbidden in (
        "OPENROUTER_API_KEY",
        "ZAI_API_KEY",
        "scripts/decide.py",
        "scripts/review.py",
        "scripts/geopolitics_paper.py",
        "scripts/evolve_auto.py",
        "polymarket_paper.py predict",
    ):
        assert forbidden not in workflow

    for forbidden in ("scripts/decide.py", "scripts/review.py", "scripts/geopolitics_paper.py"):
        assert forbidden not in cron

    assert workflow.count("agents_paper.py --manage-only") == 2
    assert cron.count("agents_paper.py --manage-only") == 2


def test_manage_only_does_not_consume_pending_decisions(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT))
    from scripts import agents_paper

    state = tmp_path / "state.json"
    decisions = tmp_path / "decisions.jsonl"
    state.write_text(json.dumps({"agents-v1": {
        "equity": 10_000.0, "positions": {}, "last_decision_ts": "",
    }}))
    decisions.write_text(json.dumps({
        "stage": "final", "logged_at": "2026-07-12T21:00:00Z",
        "proposal": {"action": "trade", "symbol": "BTC"},
    }) + "\n")

    monkeypatch.setattr(agents_paper, "STATE_FILE", state)
    monkeypatch.setattr(agents_paper, "DECISIONS", decisions)
    monkeypatch.setattr(agents_paper, "log_event", lambda event: None)
    monkeypatch.setattr(agents_paper, "open_from_decision",
                        lambda *_: (_ for _ in ()).throw(AssertionError("new entry attempted")))
    monkeypatch.setattr(sys, "argv", ["agents_paper.py", "--manage-only"])

    agents_paper.main()

    assert json.loads(state.read_text())["agents-v1"]["last_decision_ts"] == ""


def test_runtime_kill_switch_wins_even_when_provider_keys_exist(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    from scripts import llm

    monkeypatch.setenv("LLM_RUNTIME_DISABLED", "1")
    monkeypatch.setenv("ZAI_API_KEY", "not-a-real-key")

    with pytest.raises(RuntimeError, match="runtime LLM disabilitato"):
        llm._providers()


def test_runtime_is_disabled_by_default(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    from scripts import llm

    monkeypatch.delenv("LLM_RUNTIME_DISABLED", raising=False)
    monkeypatch.setenv("ZAI_API_KEY", "not-a-real-key")

    with pytest.raises(RuntimeError, match="runtime LLM disabilitato"):
        llm._providers()
