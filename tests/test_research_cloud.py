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
    assert captured["json"]["tools"][0]["web_search"]["search_engine"] == "search_pro_jina"
    assert captured["json"]["max_tokens"] == 16_000
    assert "test-only" not in json.dumps(captured["json"])


def test_zai_error_surfaces_business_code_without_message(monkeypatch):
    class Response:
        status_code = 429
        text = '{"error":{"code":"1113","message":"Insufficient balance: private detail"}}'

        def json(self):
            return json.loads(self.text)

    monkeypatch.setenv("ZAI_API_KEY", "test-only")
    monkeypatch.setattr(cloud.requests, "post", lambda *_args, **_kwargs: Response())

    try:
        cloud._zai_chat("prompt", search_prompt="primary", timeout=10)
    except cloud.ZaiQuotaUnavailable as exc:
        assert "HTTP 429 (code 1113)" in str(exc)
        assert "private detail" not in str(exc)
    else:
        raise AssertionError("Z.AI doveva fallire chiuso sul saldo insufficiente")


def test_zai_quota_falls_back_to_openrouter_deepseek_v4_pro(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {
                "model": "deepseek/deepseek-v4-pro",
                "choices": [{"message": {
                    "content": json.dumps(_maker_value()),
                    "annotations": [{"type": "url_citation", "url_citation": {
                        "url": SOURCE, "title": "Primary", "content": "Source text",
                    }}],
                }}],
                "usage": {"total_tokens": 321},
            }

    def zai_quota(*_args, **_kwargs):
        raise cloud.ZaiQuotaUnavailable("Z.AI auth/quota non disponibile: HTTP 429 (code 1113)")

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.setattr(cloud, "_zai_chat", zai_quota)
    monkeypatch.setattr(cloud.requests, "post", fake_post)
    value, sources, usage, model = cloud._research_chat("prompt", search_prompt="primary", timeout=10)

    assert value == _maker_value()
    assert sources == [{"link": SOURCE, "title": "Primary", "content": "Source text"}]
    assert usage == {"total_tokens": 321}
    assert model == "openrouter:deepseek/deepseek-v4-pro"
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["json"]["model"] == "deepseek/deepseek-v4-pro"
    assert captured["json"]["provider"] == {"require_parameters": True}
    assert captured["json"]["plugins"] == [{
        "id": "web", "engine": "exa", "max_results": 24,
        "search_prompt": "primary",
    }]
    assert "tools" not in captured["json"]
    assert not captured["json"]["model"].endswith(":online")
    assert "test-only" not in json.dumps(captured["json"])


def test_openrouter_retries_empty_content_then_returns_valid_json(monkeypatch):
    calls = []

    class Response:
        status_code = 200

        def __init__(self, content):
            self.content = content

        def json(self):
            return {
                "model": cloud.OPENROUTER_MODEL,
                "choices": [{"message": {
                    "content": self.content,
                    "annotations": [{"type": "url_citation", "url_citation": {"url": SOURCE}}],
                }}],
            }

    responses = iter([Response(""), Response(json.dumps(_maker_value()))])
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.setattr(cloud.requests, "post", lambda *_args, **_kwargs: calls.append(1) or next(responses))
    monkeypatch.setattr(cloud.time, "sleep", lambda *_args: None)

    value, sources, _usage, model = cloud._openrouter_chat("prompt", search_prompt="primary", timeout=10)

    assert value == _maker_value()
    assert sources == [{"link": SOURCE}]
    assert model == cloud.OPENROUTER_MODEL
    assert calls == [1, 1]


def test_openrouter_tool_call_without_final_json_fails_closed(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {
                    "content": None,
                    "tool_calls": [{"type": "function", "function": {"name": "search"}}],
                }}],
            }

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.setattr(cloud.requests, "post", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(cloud.time, "sleep", lambda *_args: None)

    try:
        cloud._openrouter_chat("prompt", search_prompt="primary", timeout=10)
    except RuntimeError as exc:
        assert str(exc) == "OpenRouter fallita dopo 2 tentativi: HTTP 200 senza oggetto JSON valido"
    else:
        raise AssertionError("Una tool call senza risposta finale deve fallire chiuso")


def test_maker_writes_no_artifact_after_repeated_malformed_openrouter_response(tmp_path, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(rp, "build_pack", lambda **_kwargs: _pack())
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.setattr(
        cloud, "_zai_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            cloud.ZaiQuotaUnavailable("Z.AI auth/quota non disponibile: HTTP 429 (code 1113)")),
    )

    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "not-json"}}]}

    monkeypatch.setattr(cloud.requests, "post", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(cloud.time, "sleep", lambda *_args: None)

    try:
        cloud.run_maker(tmp_path / "state.json", tmp_path / "out")
    except RuntimeError as exc:
        assert "OpenRouter fallita dopo 2 tentativi" in str(exc)
        assert "not-json" not in str(exc)
    else:
        raise AssertionError("Maker deve fallire chiuso su risposta OpenRouter non valida")
    assert not (tmp_path / "out/maker.json").exists()
    assert not (tmp_path / "out/pack.json").exists()


def test_openrouter_fallback_without_citations_fails_closed(tmp_path, monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(rp, "build_pack", lambda **_kwargs: _pack())
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.setattr(
        cloud, "_zai_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            cloud.ZaiQuotaUnavailable("Z.AI auth/quota non disponibile: HTTP 429 (code 1113)")),
    )
    monkeypatch.setattr(
        cloud, "_openrouter_chat",
        lambda *_args, **_kwargs: (_maker_value(), [], {}, cloud.OPENROUTER_MODEL),
    )

    try:
        cloud.run_maker(tmp_path / "state.json", tmp_path / "out")
    except RuntimeError as exc:
        assert "fonti verificabili" in str(exc)
    else:
        raise AssertionError("Il fallback OpenRouter deve fallire senza citation del web search")


def test_regular_zai_429_does_not_use_openrouter(monkeypatch):
    calls = []

    class Response:
        status_code = 429
        text = '{"error":{"code":"rate_limit"}}'

        def json(self):
            return json.loads(self.text)

    def fake_post(url, **_kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setenv("ZAI_API_KEY", "test-only")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.setattr(cloud.requests, "post", fake_post)
    monkeypatch.setattr(cloud.time, "sleep", lambda *_args: None)

    try:
        cloud._research_chat("prompt", search_prompt="primary", timeout=10)
    except RuntimeError as exc:
        assert "Z.AI fallita" in str(exc)
    else:
        raise AssertionError("Un rate limit non-quota Z.AI non deve cambiare provider")
    assert calls == ["https://api.z.ai/api/paas/v4/chat/completions"] * cloud.MAX_ATTEMPTS


def test_research_workflows_pass_openrouter_fallback_secret():
    root = Path(__file__).resolve().parent.parent
    for workflow_name in ("research-maker.yml", "research-checker.yml"):
        workflow = (root / ".github/workflows" / workflow_name).read_text()
        assert "OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}" in workflow
