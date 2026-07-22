"""Research OS L1 cloud runner: Z.AI primary with bounded OpenRouter fallback.

The runner is report-only. It writes only to an explicit output directory;
GitHub Actions publishes that directory as an immutable, expiring artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml

from scripts import research_pack


ROOT = Path(__file__).resolve().parent.parent
ZAI_BASE_URL = "https://api.z.ai/api/paas/v4"
ZAI_MODEL = "glm-5.1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "deepseek/deepseek-v4-pro"
MAX_ATTEMPTS = 2


class SearchProvenanceMismatch(ValueError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"fonti non presenti nei risultati web search: {missing[:3]}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: atteso oggetto JSON")
    return value


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _repo_inventory() -> dict:
    strategies = []
    for path in sorted((*ROOT.glob("strategies/*.yaml"), *ROOT.glob("strategies/generated/*.yaml"))):
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            for spec in document if isinstance(document, list) else [document]:
                if not isinstance(spec, dict) or not spec.get("id"):
                    continue
                strategies.append({
                    "id": spec["id"],
                    "status": spec.get("status", "unknown"),
                    "engine": spec.get("engine", "signal"),
                    "thesis": str(spec.get("thesis", ""))[:500],
                    "paper_symbols": spec.get("paper_symbols"),
                    "portfolio": spec.get("portfolio"),
                    "signals": [
                        signal.get("name") for signal in spec.get("signals", [])
                        if isinstance(signal, dict) and signal.get("name")
                    ],
                })
    lessons_path = ROOT / "brain/lessons.md"
    return {
        "source": "versioned repo brain plus strategy specs",
        "strategy_count": len(strategies),
        "strategies": strategies,
        "lessons_excerpt": lessons_path.read_text(encoding="utf-8")[:16_000]
        if lessons_path.exists() else "",
    }


class ZaiQuotaUnavailable(RuntimeError):
    """Z.AI errors for which the approved OpenRouter fallback may run."""


def _zai_chat(prompt: str, *, search_prompt: str, timeout: int) -> tuple[dict, list, dict, str]:
    api_key = os.environ.get("ZAI_API_KEY")
    if not api_key:
        raise RuntimeError("ZAI_API_KEY mancante")
    base_url = os.environ.get("ZAI_RESEARCH_BASE_URL", ZAI_BASE_URL).rstrip("/")
    model = os.environ.get("ZAI_RESEARCH_MODEL", ZAI_MODEL)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Restituisci esclusivamente un oggetto JSON conforme al contratto richiesto."},
            {"role": "user", "content": prompt},
        ],
        "thinking": {"type": "enabled", "clear_thinking": True},
        "response_format": {"type": "json_object"},
        "tools": [{
            "type": "web_search",
            "web_search": {
                "enable": True,
                "search_engine": "search_pro_jina",
                "search_result": True,
                "count": 24,
                "content_size": "high",
                "search_recency_filter": "noLimit",
                "search_prompt": search_prompt,
            },
        }],
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 16_000,
    }
    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept-Language": "en-US,en",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(15, timeout),
            )
        except requests.RequestException as exc:
            last_error = f"rete: {type(exc).__name__}"
            if attempt + 1 < MAX_ATTEMPTS:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"Z.AI non raggiungibile: {last_error}") from exc
        if response.status_code == 200:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            value = json.loads(content) if isinstance(content, str) else content
            if not isinstance(value, dict):
                raise RuntimeError("Z.AI non ha restituito un oggetto JSON")
            return value, body.get("web_search") or [], body.get("usage") or {}, body.get("model", model)
        message = (response.text or "")[:300]
        try:
            error_code = str((response.json().get("error") or {}).get("code") or "").strip()
        except (AttributeError, TypeError, ValueError):
            error_code = ""
        error_suffix = f" (code {error_code})" if error_code else ""
        if (response.status_code in (401, 402, 403) or error_code == "1113"
                or "insufficient" in message.lower()):
            raise ZaiQuotaUnavailable(
                f"Z.AI auth/quota non disponibile: HTTP {response.status_code}{error_suffix}")
        last_error = f"HTTP {response.status_code}{error_suffix}"
        if response.status_code != 429 and response.status_code < 500:
            raise RuntimeError(f"Z.AI richiesta rifiutata: {last_error}")
        if attempt + 1 < MAX_ATTEMPTS:
            time.sleep(2**attempt)
    raise RuntimeError(f"Z.AI fallita dopo {MAX_ATTEMPTS} tentativi: {last_error}")


def _openrouter_search_results(message: dict) -> list[dict]:
    results = []
    for annotation in message.get("annotations") or []:
        if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
            continue
        citation = annotation.get("url_citation")
        if not isinstance(citation, dict) or not isinstance(citation.get("url"), str):
            continue
        result = {"link": citation["url"]}
        for key in ("title", "content"):
            if isinstance(citation.get(key), str):
                result[key] = citation[key]
        results.append(result)
    return results


def _openrouter_chat(
    prompt: str, *, search_prompt: str, timeout: int, enable_web: bool = True,
) -> tuple[dict, list, dict, str]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY mancante")
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Restituisci esclusivamente un oggetto JSON conforme al contratto richiesto.",
            },
            {
                "role": "user",
                "content": (
                    f"{prompt}\n\nDIRETTIVA DI RICERCA:\n{search_prompt}"
                    if enable_web else prompt
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "provider": {"require_parameters": True},
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 16_000,
    }
    if enable_web:
        payload["plugins"] = [{
            "id": "web",
            "engine": "exa",
            "max_results": 24,
            "search_prompt": search_prompt,
        }]
    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(15, timeout),
            )
        except requests.RequestException as exc:
            last_error = f"rete: {type(exc).__name__}"
            if attempt + 1 < MAX_ATTEMPTS:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"OpenRouter non raggiungibile: {last_error}") from exc
        if response.status_code == 200:
            try:
                body = response.json()
                message = body["choices"][0]["message"]
                content = message["content"]
                value = json.loads(content) if isinstance(content, str) else content
                if not isinstance(value, dict):
                    raise ValueError("contenuto non JSON object")
            except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
                last_error = "HTTP 200 senza oggetto JSON valido"
                if attempt + 1 < MAX_ATTEMPTS:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(
                    f"OpenRouter fallita dopo {MAX_ATTEMPTS} tentativi: {last_error}") from exc
            return value, _openrouter_search_results(message), body.get("usage") or {}, body.get("model", OPENROUTER_MODEL)
        try:
            error_code = str((response.json().get("error") or {}).get("code") or "").strip()
        except (AttributeError, TypeError, ValueError):
            error_code = ""
        error_suffix = f" (code {error_code})" if error_code else ""
        last_error = f"HTTP {response.status_code}{error_suffix}"
        if response.status_code != 429 and response.status_code < 500:
            raise RuntimeError(f"OpenRouter richiesta rifiutata: {last_error}")
        if attempt + 1 < MAX_ATTEMPTS:
            time.sleep(2**attempt)
    raise RuntimeError(f"OpenRouter fallita dopo {MAX_ATTEMPTS} tentativi: {last_error}")


def _research_chat(prompt: str, *, search_prompt: str, timeout: int) -> tuple[dict, list, dict, str]:
    try:
        value, search_results, usage, model = _zai_chat(
            prompt, search_prompt=search_prompt, timeout=timeout)
        return value, search_results, usage, f"zai:{model}"
    except ZaiQuotaUnavailable as exc:
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise RuntimeError(f"{exc}; OPENROUTER_API_KEY mancante") from exc
        value, search_results, usage, model = _openrouter_chat(
            prompt, search_prompt=search_prompt, timeout=timeout)
        return value, search_results, usage, f"openrouter:{model}"


def _normalized_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def _validate_search_provenance(maker: dict, search_results: list) -> None:
    surfaced = {
        _normalized_url(str(result.get("link", "")))
        for result in search_results if isinstance(result, dict) and result.get("link")
    }
    if not surfaced:
        raise ValueError("web search non ha restituito fonti verificabili")
    missing = sorted({
        url for family in maker.get("research_families", [])
        for url in family.get("source_urls", [])
        if _normalized_url(url) not in surfaced
    })
    if missing:
        raise SearchProvenanceMismatch(missing)


def _maker_fixed(value: dict, pack: dict, run_id: str, model: str) -> dict:
    value = dict(value)
    value.update({
        "kind": research_pack.MAKER_KIND,
        "pack_id": pack["pack_id"],
        "created_at": _now().isoformat(),
        "maker_run_id": run_id,
        "model": model,
        "guardrails": dict(research_pack.GUARDRAILS),
    })
    inventory = dict(value.get("inventory") or {})
    inventory["note_path"] = "brain/ plus strategies/ (versioned cloud inventory)"
    inventory["checked_at"] = _now().isoformat()
    value["inventory"] = inventory
    return value


def _checker_fixed(value: dict, pack: dict, maker: dict, run_id: str) -> dict:
    value = dict(value)
    value.update({
        "kind": research_pack.CHECKER_KIND,
        "pack_id": pack["pack_id"],
        "maker_sha256": research_pack.content_hash(maker),
        "maker_run_id": maker["maker_run_id"],
        "checked_at": _now().isoformat(),
        "checker_run_id": run_id,
    })
    return value


def _metadata(role: str, run_id: str, model: str, usage: dict, search_results: list) -> dict:
    return {
        "role": role,
        "run_id": run_id,
        "model": model,
        "created_at": _now().isoformat(),
        "usage": usage,
        "search_result_count": len(search_results),
        "guardrails": dict(research_pack.GUARDRAILS),
    }


def run_maker(state_file: str | Path, out_dir: str | Path) -> dict:
    out = Path(out_dir)
    pack = research_pack.build_pack(state_file=state_file)
    run_id = f"maker-{os.environ.get('GITHUB_RUN_ID', uuid.uuid4().hex)}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    contract = (ROOT / "prompts/research_os/contracts.md").read_text(encoding="utf-8")
    base_prompt = (
        "Esegui un Daily Research Maker L1 source-first e report-only. Esplora 5-8 famiglie "
        "distinte. Usa soltanto fonti primarie realmente restituite dal web search; copia "
        "gli URL esatti. NO_CANDIDATE e il default quando novelty o dati point-in-time non "
        "reggono. Includi almeno due famiglie materialmente distinte ma implementabili, senza "
        "nuovo codice o nuove fonti, come mutazioni one-shot delle portfolio attive basate su "
        "xsmom, tsmom o highvol. Se selezioni una candidata, preferisci una di queste solo quando "
        "il meccanismo resta fedele e il data contract usa dati gia disponibili; non spacciare un "
        "ritocco parametrico per novelty. Le idee event-driven o microstrutturali restano blocked "
        "se manca il runner. Non calcolare P&L, non creare strategie e non proporre operazioni.\n\n"
        f"CONTRATTO:\n{contract}\n\nPACK:\n{research_pack.render_prompt(pack)}\n\n"
        f"INVENTARIO CLOUD VERSIONATO:\n{json.dumps(_repo_inventory(), ensure_ascii=False)}"
    )
    error = None
    for attempt in range(MAX_ATTEMPTS):
        prompt = base_prompt if error is None else f"{base_prompt}\n\nCorreggi questo errore del validatore: {error}"
        value, search_results, usage, model = _research_chat(
            prompt,
            search_prompt=(
                "Cerca fonti primarie correnti: paper originali, documentazione exchange/protocollo, "
                "regolatori o proprietari dei dataset. Escludi aggregatori, social e marketing."
            ),
            timeout=900,
        )
        maker = _maker_fixed(value, pack, run_id, model)
        try:
            research_pack.validate_maker(pack, maker, now=_now())
            _validate_search_provenance(maker, search_results)
            break
        except (KeyError, TypeError, ValueError) as exc:
            error = str(exc)
            if attempt + 1 == MAX_ATTEMPTS:
                raise RuntimeError(f"Maker invalido dopo {MAX_ATTEMPTS} tentativi: {error}") from exc
    _write_json(out / "pack.json", pack)
    _write_json(out / "maker.json", maker)
    _write_json(out / "maker-search.json", search_results)
    _write_json(out / "metadata.json", _metadata("maker", run_id, model, usage, search_results))
    return {"pack_id": pack["pack_id"], "outcome": maker["outcome"], "run_id": run_id}


def run_checker(input_dir: str | Path, out_dir: str | Path) -> dict:
    source, out = Path(input_dir), Path(out_dir)
    pack, maker = _read_json(source / "pack.json"), _read_json(source / "maker.json")
    research_pack.validate_maker(pack, maker, now=_now())
    run_id = f"checker-{os.environ.get('GITHUB_RUN_ID', uuid.uuid4().hex)}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    contract = (ROOT / "prompts/research_os/contracts.md").read_text(encoding="utf-8")
    base_prompt = (
        "Sei il Checker L1 indipendente. Cerca motivi concreti per REJECT; non migliorare il Maker. "
        "Verifica novelty, distinzione delle famiglie, qualita primaria delle fonti e fattibilita "
        "point-in-time usando il web search. APPROVE solo con tutti i check veri e zero blocker. "
        "Nessun verdetto autorizza P&L, strategia, paper/live o capitale.\n\n"
        f"CONTRATTO:\n{contract}\n\nPACK:\n{json.dumps(pack, ensure_ascii=False)}\n\n"
        f"MAKER:\n{json.dumps(maker, ensure_ascii=False)}\n\n"
        f"INVENTARIO CLOUD VERSIONATO:\n{json.dumps(_repo_inventory(), ensure_ascii=False)}"
    )
    error = None
    for attempt in range(MAX_ATTEMPTS):
        prompt = base_prompt if error is None else f"{base_prompt}\n\nCorreggi questo errore del validatore: {error}"
        value, search_results, usage, model = _research_chat(
            prompt,
            search_prompt="Verifica gli URL citati dal Maker e cerca fonti primarie che confermino o falsifichino i meccanismi.",
            timeout=480,
        )
        checker = _checker_fixed(value, pack, maker, run_id)
        try:
            result = research_pack.validate_checker(pack, maker, checker, now=_now())
            _validate_search_provenance(maker, search_results)
            break
        except SearchProvenanceMismatch as exc:
            trusted_checks = {
                "pack_integrity", "maker_schema", "identity_separation",
                "scope_report_only", "checker_no_forbidden_writes",
            }
            checker = _checker_fixed({
                "verdict": "REJECT",
                "blockers": [
                    f"Fonte Maker non riattestata dalla ricerca web indipendente: {url}"
                    for url in exc.missing
                ],
                "notes": (
                    "REJECT fail-closed: la ricerca web indipendente non ha riattestato "
                    f"{len(exc.missing)} fonti Maker."
                ),
                "checks": {
                    check: check in trusted_checks for check in research_pack.CHECKS
                },
            }, pack, maker, run_id)
            result = research_pack.validate_checker(pack, maker, checker, now=_now())
            break
        except (KeyError, TypeError, ValueError) as exc:
            error = str(exc)
            if attempt + 1 == MAX_ATTEMPTS:
                raise RuntimeError(f"Checker invalido dopo {MAX_ATTEMPTS} tentativi: {error}") from exc
    _write_json(out / "checker.json", checker)
    _write_json(out / "checker-search.json", search_results)
    _write_json(out / "metadata.json", _metadata("checker", run_id, model, usage, search_results))
    return {"pack_id": pack["pack_id"], "verdict": result["verdict"], "run_id": run_id}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    maker = commands.add_parser("maker")
    maker.add_argument("--state-file", required=True)
    maker.add_argument("--out-dir", required=True)
    checker = commands.add_parser("checker")
    checker.add_argument("--input-dir", required=True)
    checker.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    result = (run_maker(args.state_file, args.out_dir) if args.command == "maker"
              else run_checker(args.input_dir, args.out_dir))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
