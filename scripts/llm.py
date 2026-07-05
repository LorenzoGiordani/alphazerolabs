"""Layer LLM — GLM via catena provider: Z AI coding plan (default) → OpenRouter (fallback).

Provider chain, endpoint OpenAI-compatible in entrambi i casi. ask() prova il
provider primario (Z AI coding plan); se fallisce (auth/quota/rete/errore
modello) degrada automaticamente al fallback (OpenRouter) — trasparente al
chiamante. Un provider è saltato se manca la sua API key, quindi la catena si
riduce a ciò che è configurato. Punto d'ingresso unico ask() per tutta la pipeline.

Capacità del layer:
  • EFFORT MULTI-LIVELLO — max/medium/low/none mappati a reasoning_effort
    (high/medium/low/omesso). I ruoli "pesanti" (Analyst, Strategist, evolve)
    usano max; i ruoli di veto/checkbox (Bull, Bear, Risk, Auditor) usano
    low/medium → risparmio token/latenza a parità di decisioni.
  • STRUCTURED OUTPUT NATIVO — passa `schema=<JSON Schema>` e la risposta torna
    come dict già validato via tool use (tool_choice forzato). Niente più
    parsing regex fragile: il modello è vincolato dallo schema.
  • TRACING — ogni chiamata logga su paper/llm_calls.jsonl (role, model, effort,
    tokens, latency). Base per osservabilità e ottimizzazione.
  • CACHE APPLICATIVO — cache=True memorizza il risultato per hash(prompt) in
    paper/llm_cache/. Determinismo + costo zero per eval/test/dedup. Il caching
    lato-API non è supportato, quindi è tutto client-side.

Config (priorità: .env del progetto → env di processo):
  Provider primario — Z AI coding plan:
    ZAI_API_KEY          api key Z AI coding plan (header Authorization: Bearer).
    ZAI_BASE_URL         default https://api.z.ai/api/coding/paas/v4
    ZAI_MODEL            default glm-5.2
  Provider fallback — OpenRouter:
    OPENROUTER_API_KEY   api key OpenRouter (header Authorization: Bearer).
    OPENROUTER_BASE_URL  default https://openrouter.ai/api/v1
    OPENROUTER_MODEL     default z-ai/glm-5.2-20260616 (canonical slug pinnato)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "z-ai/glm-5.2-20260616"

# Provider primario: Z AI coding plan (endpoint OpenAI-compatible /chat/completions).
DEFAULT_ZAI_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
DEFAULT_ZAI_MODEL = "glm-5.2"

# Effort → reasoning_effort (enum OpenRouter). "none" = reasoning omesso (modello
# non ragiona). ponytail: il vecchio GLM_THINKING_BUDGET numerico non ha senso su
# OpenRouter (enum, non budget token) — droppato. Upgrade path: se servirà budget
# fine-grained, OpenRouter espone `reasoning: {max_tokens: N}` per alcuni modelli.
EFFORT_TO_REASONING = {"max": "high", "medium": "medium", "low": "low", "none": None}
OUTPUT_RESERVE = 16384  # token di output finale
# Su OpenRouter max_tokens limita TUTTI i completion token (reasoning + content).
# Con reasoning on, serve spazio per il chain-of-thought + la risposta. Ponytail:
# uso un budget generoso per effort alto (il modello non lo consumerà tutto se non
# serve). Upgrade path: OpenRouter espone `reasoning: {max_tokens: N}` per budget
# fine-grained, ma enum effort è più semplice e sufficiente.
EFFORT_MAX_TOKENS = {"max": 48000, "medium": 16000, "low": 8000, "none": OUTPUT_RESERVE}

# Pattern di errore LLM NON transiente (quota/auth/credit): un retry non li
# risolve. Derivati da errori reali OpenRouter + residui generici. Testabili
# senza rete. NB: "rate_limit_error" NON è qui — un 429 da burst passa col
# backoff, e il ramo status-code in _post lo ritenta già.
NON_TRANSIENT_ERRORS = (
    "usage limit reached", "weekly usage limit", "resets in",
    "insufficient balance", "insufficient credit", "insufficient credits",
    "insufficient_quota",
    "unauthorized", "invalid api key", "invalid_api_key",
    "authentication failed", "authentication_failed", "permission_denied",
    "not_entitled", "no credit", "payment required",
)

LLM_CALLS_LOG = ROOT / "paper/llm_calls.jsonl"


def _dotenv_get(key: str) -> str | None:
    env = ROOT / ".env"
    if not env.exists():
        return None
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _config(key: str, default: str | None = None) -> str | None:
    # Priorità: .env del PROGETTO vince sull'env di processo. Il .env è la fonte
    # di verità locale (riproducibile, allineata al repo/CI). L'env di processo
    # (es. export nello zshrc) può contenere chiavi stale/alternative di altri
    # progetti e sovrascrivere silenziosamente — qui lo preveniamo.
    val = _dotenv_get(key) or os.environ.get(key)
    return val if val else default


def get_api_key() -> str:
    key = _config("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY mancante: imposta il secret/env, oppure scrivi "
            "OPENROUTER_API_KEY=... in .env.")
    return key


def _providers() -> list[dict]:
    """Catena provider ordinata: Z AI coding plan (default) → OpenRouter (fallback).

    Un provider entra in catena solo se la sua API key è configurata: così se
    ZAI_API_KEY manca, la catena resta OpenRouter-only (comportamento invariato),
    e viceversa. ask() prova i provider in ordine, degradando al successivo su
    qualsiasi errore."""
    chain: list[dict] = []
    zai_key = _config("ZAI_API_KEY")
    if zai_key:
        chain.append({"name": "zai", "api_key": zai_key,
                      "base_url": _config("ZAI_BASE_URL", DEFAULT_ZAI_BASE_URL),
                      "model": _config("ZAI_MODEL", DEFAULT_ZAI_MODEL)})
    or_key = _config("OPENROUTER_API_KEY")
    if or_key:
        chain.append({"name": "openrouter", "api_key": or_key,
                      "base_url": _config("OPENROUTER_BASE_URL", DEFAULT_BASE_URL),
                      "model": _config("OPENROUTER_MODEL", DEFAULT_MODEL)})
    if not chain:
        raise RuntimeError(
            "nessun provider LLM configurato: imposta ZAI_API_KEY (Z AI coding plan) "
            "e/o OPENROUTER_API_KEY, via env o .env.")
    return chain


def reasoning_effort(effort: str) -> str | None:
    """Mappa effort (max/medium/low/none) → reasoning_effort enum OpenRouter.
    None = reasoning omesso (modello non ragiona)."""
    return EFFORT_TO_REASONING.get(effort, None)


def max_tokens_for(effort: str) -> int:
    """max_tokens per effort. Con reasoning on serve spazio per il chain-of-thought."""
    return EFFORT_MAX_TOKENS.get(effort, OUTPUT_RESERVE)


# ─── text helpers ────────────────────────────────────────────────────────────

def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()


def extract_text(message: dict) -> str:
    """Estrae il testo dalla risposta OpenAI (choices[0].message.content).
    Su OpenRouter il reasoning è separato in message.reasoning, non in content."""
    return (message.get("content") or "").strip()


def extract_tool_input(message: dict):
    """Estrae l'input del primo tool_call (structured output). arguments è una
    stringa JSON su OpenAI format → parsata. Fallback robusto via parse_json."""
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {})
        args = fn.get("arguments")
        if args:
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                return parse_json(args)
    return None


def parse_json(text: str):
    """Fallback robusto: JSON anche circondato da prosa/fence."""
    text = _strip_fence(text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        text = m.group(0)
    return json.loads(text)


# ─── tracing ─────────────────────────────────────────────────────────────────

def _trace(record: dict) -> None:
    record["ts"] = datetime.now(timezone.utc).isoformat()
    try:
        LLM_CALLS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LLM_CALLS_LOG.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass  # il tracing non deve mai rompere una chiamata


# ─── cache applicativo (content-hash) ────────────────────────────────────────

def _cache_dir() -> Path | None:
    d = _config("GLM_CACHE_DIR", "paper/llm_cache")
    if not d:
        return None
    return (ROOT / d) if not Path(d).is_absolute() else Path(d)


def _cache_ttl() -> int:
    try:
        return max(0, int(_config("GLM_CACHE_TTL", "86400")))
    except ValueError:
        return 86400


def _cache_key(model: str, system, prompt: str, effort: str, schema, temperature) -> str:
    payload = json.dumps({"m": model, "s": system, "p": prompt, "e": effort,
                          "sc": json.dumps(schema, sort_keys=True) if schema else None,
                          "t": temperature}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_get(key: str):
    d = _cache_dir()
    if not d:
        return None
    f = d / f"{key}.json"
    if not f.exists():
        return None
    try:
        rec = json.loads(f.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    ttl = _cache_ttl()
    age = time.time() - rec.get("ts_epoch", 0)
    if ttl and age > ttl:
        return None
    return rec.get("result")


def _cache_put(key: str, result, usage: dict) -> None:
    d = _cache_dir()
    if not d:
        return
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{key}.json").write_text(json.dumps(
            {"result": result, "usage": usage, "ts_epoch": time.time(),
             "ts": datetime.now(timezone.utc).isoformat()}, default=str))
    except OSError:
        pass


# ─── HTTP ────────────────────────────────────────────────────────────────────

def _is_non_transient(text: str) -> str | None:
    low = text.lower()
    for p in NON_TRANSIENT_ERRORS:
        if p in low:
            return p
    return None


def _post(base_url: str, api_key: str, payload: dict, timeout: int) -> dict:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"content-type": "application/json",
               "authorization": f"Bearer {api_key}"}
    last_err = None
    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as e:
            last_err = f"rete irraggiungibile: {type(e).__name__}: {str(e)[:160]}"
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            return r.json()
        body = (r.text or "")[:500]
        marker = _is_non_transient(body) or _is_non_transient(f"{r.status_code} {body}")
        if marker:
            raise RuntimeError(f"GLM-5.2 non disponibile (non transiente: {marker}): "
                               f"HTTP {r.status_code} {body[:200]}")
        if r.status_code in (401, 403):
            raise RuntimeError(f"auth OpenRouter fallita (HTTP {r.status_code}): {body[:200]}")
        if r.status_code == 429 or 500 <= r.status_code < 600:
            last_err = f"HTTP {r.status_code} {body[:200]}"
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"chiamata LLM fallita (HTTP {r.status_code}): {body[:200]}")
    raise RuntimeError(f"GLM-5.2 non raggiungibile dopo 3 tentativi: {last_err}")


def ask(prompt: str, system: str | None = None, as_json: bool = False,
        effort: str = "max", schema: dict | None = None, schema_name: str = "answer",
        role: str | None = None, cache: bool = False, temperature: float | None = None,
        timeout: int = 300):
    """Una chiamata a GLM-5.2 via OpenRouter.

    - effort: max/medium/low/none → reasoning_effort (high/medium/low/omesso).
    - schema: se passato (JSON Schema dict), la risposta è structured via tool use
      forzato → ritorna un dict già validato (as_json implicito, niente parsing).
    - as_json: fallback (senza schema) — parsare JSON dal testo libero.
    - role: etichetta per il tracing (es. "strategist").
    - cache: se True, memoizza per hash(prompt) — determinismo + costo zero su
      ripetizioni (eval, test, re-run).
    - temperature: inoltrata all'API (per self-consistency: più alto = più varianza).

    Ritorna str (testo), oppure dict/list se schema/as_json. Solleva RuntimeError
    su errori di quota/auth/rete con messaggio actionable."""
    providers = _providers()

    # Cache key logico: ancorato al modello del provider PRIMARIO (l'intento),
    # così l'hit non dipende da quale provider ha effettivamente risposto.
    key = _cache_key(providers[0]["model"], system, prompt, effort, schema, temperature)
    if cache:
        hit = _cache_get(key)
        if hit is not None:
            _trace({"role": role, "model": providers[0]["model"], "effort": effort,
                    "ok": True, "cached": True, "latency_s": 0.0, "usage": {}})
            return hit

    reasoning = reasoning_effort(effort)
    max_tokens = max_tokens_for(effort)

    # OpenAI format: system è un messaggio in coda, non top-level.
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    base_payload: dict = {"max_tokens": max_tokens, "messages": messages}
    if temperature is not None:
        base_payload["temperature"] = temperature
    if reasoning is not None:
        base_payload["reasoning_effort"] = reasoning
    if schema:
        base_payload["tools"] = [{"type": "function", "function": {
            "name": schema_name, "description": f"Output strutturato per {schema_name}",
            "parameters": schema}}]
        base_payload["tool_choice"] = {"type": "function", "function": {"name": schema_name}}

    # Catena provider: prova ciascuno in ordine; degrada al successivo su errore.
    errors: list[str] = []
    for i, prov in enumerate(providers):
        model = prov["model"]
        payload = {**base_payload, "model": model}
        t0 = time.time()
        try:
            data = _post(prov["base_url"], prov["api_key"], payload, timeout)
            message = data["choices"][0]["message"]
            if schema:
                result = extract_tool_input(message)
                if result is None:  # safety net: il modello a volte risponde in testo
                    txt = extract_text(message)
                    result = parse_json(txt) if txt else None
                if result is None:
                    raise RuntimeError("risposta senza tool_use e senza JSON testuale")
            elif as_json:
                result = parse_json(extract_text(message))
            else:
                result = extract_text(message)
                if not result:
                    raise RuntimeError("risposta LLM senza testo")
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
            _trace({"role": role, "provider": prov["name"], "model": model, "effort": effort,
                    "ok": False, "cached": False, "fallback": i > 0,
                    "latency_s": round(time.time() - t0, 2), "error": err, "usage": {}})
            errors.append(f"{prov['name']}({model}): {err}")
            continue  # prova il prossimo provider della catena

        latency = round(time.time() - t0, 2)
        usage = data.get("usage", {}) if data else {}
        # usage: prompt_tokens/completion_tokens (+ reasoning_tokens in
        # completion_tokens_details per i modelli reasoning).
        ctd = usage.get("completion_tokens_details", {}) or {}
        _trace({"role": role, "provider": prov["name"], "model": model, "effort": effort,
                "ok": True, "cached": False, "fallback": i > 0, "latency_s": latency,
                "reasoning_effort": reasoning, "schema": schema_name if schema else None,
                "usage": {"in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens"),
                          "reasoning": ctd.get("reasoning_tokens", 0)}})
        if cache:
            _cache_put(key, result, usage)
        return result

    raise RuntimeError("tutti i provider LLM falliti — " + " | ".join(errors))


def model_label() -> str:
    """Modello del provider primario configurato (Z AI se presente, altrimenti OpenRouter)."""
    return _providers()[0]["model"]


if __name__ == "__main__":
    _p = _providers()
    print(f"[llm] catena provider: " + " → ".join(f"{p['name']}({p['model']})" for p in _p))
    print(f"[llm] primario={_p[0]['name']} modello={_p[0]['model']} base={_p[0]['base_url']}")
    out = ask("Rispondi con una sola parola: OK", effort="max", role="smoke")
    print(f"[llm] text: {out!r}")
    # structured output test
    sch = {"type": "object",
           "properties": {"ok": {"type": "boolean"}, "n": {"type": "integer"}},
           "required": ["ok", "n"]}
    st = ask("Rispondi ok=true e n=42", schema=sch, schema_name="smoke", role="smoke_struct")
    print(f"[llm] struct: {st!r} (type {type(st).__name__})")
