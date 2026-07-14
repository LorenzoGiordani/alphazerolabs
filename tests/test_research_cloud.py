import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import research_cloud as cloud
from scripts import research_pack as rp


NOW = datetime(2026, 7, 14, 5, 15, tzinfo=timezone.utc)
SOURCE = "https://example.org/primary"


def _pack():
    census = [{"symbol": "BTC"}]
    return rp._with_pack_id({
        "kind": rp.PACK_KIND,
        "generated_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
        "universe": {"census": census, "census_sha256": rp.content_hash(census)},
    })


def _maker_value():
    return {
        "outcome": "NO_CANDIDATE",
        "inventory": {"consumed_strategy_ids": [], "novelty_summary": "Nessuna famiglia supera i gate."},
        "research_families": [{
            "family_id": f"family-{index}",
            "title": f"Family {index}",
            "hypothesis": "Ipotesi falsificabile",
            "mechanism": f"Meccanismo distinto {index}",
            "data_requirements": ["dataset point-in-time"],
            "source_urls": [SOURCE],
            "novelty_status": "novel",
            "data_feasibility": "blocked",
            "blockers": ["dataset non disponibile point-in-time"],
        } for index in range(1, 6)],
        "candidate": None,
    }


def _checker_value():
    return {
        "verdict": "APPROVE_NO_CANDIDATE",
        "blockers": [],
        "notes": "No-candidate coerente e fonti verificate.",
        "checks": {key: True for key in rp.CHECKS},
    }


def _patch_common(monkeypatch):
    monkeypatch.setattr(cloud, "_now", lambda: NOW + timedelta(minutes=30))
    monkeypatch.setattr(cloud, "_repo_inventory", lambda: {"strategies": [], "lessons_excerpt": ""})
    monkeypatch.setattr(rp, "render_prompt", lambda _pack_value: "bounded pack")


def test_maker_writes_valid_artifact_with_search_provenance(tmp_path, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(rp, "build_pack", lambda **_kwargs: _pack())
    monkeypatch.setattr(cloud, "_zai_chat", lambda *_args, **_kwargs: (
        _maker_value(), [{"link": SOURCE, "title": "Primary"}], {"total_tokens": 123}, "glm-5.1",
    ))
    result = cloud.run_maker(tmp_path / "state.json", tmp_path / "out")
    maker = json.loads((tmp_path / "out/maker.json").read_text())
    assert result["outcome"] == "NO_CANDIDATE"
    assert maker["model"] == "zai:glm-5.1"
    assert maker["guardrails"] == rp.GUARDRAILS
    assert json.loads((tmp_path / "out/metadata.json").read_text())["search_result_count"] == 1


def test_maker_fails_closed_when_source_was_not_surfaced(tmp_path, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(rp, "build_pack", lambda **_kwargs: _pack())
    monkeypatch.setattr(cloud, "_zai_chat", lambda *_args, **_kwargs: (
        _maker_value(), [{"link": "https://example.org/different"}], {}, "glm-5.1",
    ))
    try:
        cloud.run_maker(tmp_path / "state.json", tmp_path / "out")
    except RuntimeError as exc:
        assert "fonti non presenti" in str(exc)
    else:
        raise AssertionError("Maker doveva fallire senza provenance web-search")


def test_checker_is_separate_and_valid(tmp_path, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(rp, "build_pack", lambda **_kwargs: _pack())
    responses = iter([
        (_maker_value(), [{"link": SOURCE}], {}, "glm-5.1"),
        (_checker_value(), [{"link": SOURCE}], {"total_tokens": 80}, "glm-5.1"),
    ])
    monkeypatch.setattr(cloud, "_zai_chat", lambda *_args, **_kwargs: next(responses))
    cloud.run_maker(tmp_path / "state.json", tmp_path / "maker")
    result = cloud.run_checker(tmp_path / "maker", tmp_path / "checker")
    maker = json.loads((tmp_path / "maker/maker.json").read_text())
    checker = json.loads((tmp_path / "checker/checker.json").read_text())
    assert result["verdict"] == "APPROVE_NO_CANDIDATE"
    assert checker["checker_run_id"] != maker["maker_run_id"]


def test_checker_fails_closed_without_independent_search(tmp_path, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(rp, "build_pack", lambda **_kwargs: _pack())
    responses = iter([
        (_maker_value(), [{"link": SOURCE}], {}, "glm-5.1"),
        (_checker_value(), [], {}, "glm-5.1"),
        (_checker_value(), [], {}, "glm-5.1"),
    ])
    monkeypatch.setattr(cloud, "_zai_chat", lambda *_args, **_kwargs: next(responses))
    cloud.run_maker(tmp_path / "state.json", tmp_path / "maker")
    try:
        cloud.run_checker(tmp_path / "maker", tmp_path / "checker")
    except RuntimeError as exc:
        assert "fonti verificabili" in str(exc)
    else:
        raise AssertionError("Checker doveva fallire senza ricerca indipendente")


def test_zai_request_uses_general_api_and_web_search(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {
                "model": "glm-5.1",
                "choices": [{"message": {"content": "{}"}}],
                "web_search": [],
                "usage": {},
            }

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setenv("ZAI_API_KEY", "test-only")
    monkeypatch.delenv("ZAI_RESEARCH_BASE_URL", raising=False)
    monkeypatch.setattr(cloud.requests, "post", fake_post)
    cloud._zai_chat("prompt", search_prompt="primary", timeout=10)
    assert captured["url"].startswith("https://api.z.ai/api/paas/v4/")
    assert captured["json"]["tools"][0]["type"] == "web_search"
    assert captured["json"]["max_tokens"] == 16_000
    assert "test-only" not in json.dumps(captured["json"])
