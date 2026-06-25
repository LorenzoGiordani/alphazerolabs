"""Pipeline agenti v1 — una decisione di trading end-to-end (Step 3).

Ruoli: Research+Analyst (brief) → Bull vs Bear (debate) → Strategist (proposta
JSON) → hard limit nel codice (veto deterministico, insindacabile) → Risk
Manager LLM (veto qualitativo). Output: decisione nel journal.

Modi:
  uv run scripts/decide.py BTC,ETH,SOL              # full auto via glm-5.2 (opencode-go)
  uv run scripts/decide.py BTC,ETH,SOL --pack       # stampa contesto+prompt (LLM = sessione Claude Code)
  uv run scripts/decide.py BTC,ETH,SOL --check p.json  # valida proposta Strategist e logga

Hard limits (non negoziabili dall'LLM): leva ≤2, rischio ≤1% equity/trade,
stop obbligatorio 0.5-8%, max 3 posizioni, solo simboli del contesto.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.risk import atr_pct
from backtest.signals import SIGNALS
from backtest.walkforward import regimes
from pipeline.live import fetch_live, news_headlines, open_interest_24h

DECISIONS = ROOT / "paper/decisions.jsonl"

HARD_LIMITS = {
    "max_leverage": 2.0,
    "max_risk_per_trade_pct": 1.0,
    "stop_pct_range": (0.5, 8.0),
    "min_stop_atr_mult": 1.0,   # lo stop deve stare FUORI dal rumore: >= 1*ATR% dell'asset
    "max_concurrent_positions": 3,
}

ROLES = {
    "analyst": (
        "Sei il Market Analyst di un desk crypto. Dal contesto (prezzi, funding, OI, "
        "taker flow, segnali, news) produci un brief: 1) regime di mercato complessivo, "
        "2) per ogni asset: lettura quantitativa in 1-2 righe (posizionamento, flussi, struttura), "
        "3) i 2-3 asset con il setup più interessante e perché. "
        "PRIORITÀ: il campo `lux_confluence` è l'edge sistematico più robusto e validato del desk "
        "(trend+liquidazioni reali+forecast Kronos concordi). Quando `aligned`=true segnala il setup a "
        "più alta convinzione su quell'asset, nella sua `direction`; trattalo come primario. "
        "Niente raccomandazioni di trade. Max 350 parole."
    ),
    "bull": (
        "Sei il ricercatore BULL. Dal brief dell'Analyst, argomenta la migliore tesi LONG "
        "possibile (asset specifico, catalizzatori, posizionamento). Sii aggressivo ma onesto sui rischi. Max 150 parole."
    ),
    "bear": (
        "Sei il ricercatore BEAR. Dal brief dell'Analyst, argomenta la migliore tesi SHORT "
        "possibile (asset specifico, catalizzatori, posizionamento). Sii aggressivo ma onesto sui rischi. Max 150 parole."
    ),
    "strategist": (
        "Sei lo Strategist. Hai il brief, il dibattito bull/bear, la confluenza LUX e le LEZIONI dal "
        "journal (post-mortem di trade passati): rispettale o motiva esplicitamente perché non si applicano. "
        "Favorisci i setup con `lux_confluence.aligned`=true (edge validato, top-conviction) e allinea la "
        "direction alla sua; se vai contro la confluenza LUX, motivalo esplicitamente nella tesi. "
        "Decidi: UN trade o nessuno (nessun trade è una decisione rispettabile). "
        "STOP: deve stare FUORI dal rumore — usa stop_pct >= `atr_pct` dell'asset (nel contesto) e "
        "mai più stretto dell'invalidazione della tesi. Stop dentro 1 ATR = noise-stop garantito "
        "(lezioni execution_issue ricorrenti). TIME_STOP: coerente con l'orizzonte della tesi — se i "
        "catalizzatori maturano in giorni (macro/rotazione), usa >=72h, non 24h. Rispondi SOLO con JSON: "
        '{"action": "trade"|"no_trade", "symbol": str, "direction": "long"|"short", '
        '"leverage": float, "risk_pct": float, "stop_pct": float, "target_r": float, '
        '"time_stop_h": int, "thesis": str (3-4 frasi, falsificabile), "invalidation": str (cosa la smentisce)}'
    ),
    "risk": (
        "Sei il Risk Manager, adversariale per mandato: sei premiato per trovare difetti, "
        "non per accondiscendere. Valuta la proposta: qualità della tesi, timing, correlazione col "
        "portafoglio, funding contro, liquidità. Rispondi SOLO con JSON: "
        '{"verdict": "approve"|"reduce"|"veto", "size_multiplier": float, "notes": str}'
    ),
}


def _strip_fence(text: str) -> str:
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text


# (giugno 2026) consolidamento LLM su singola key glm: il path claude è stato
# rimosso. _ask ora usa solo opencode-go/glm-5.2. La funzione _ask_claude è
# recuperabile via git se si volesse ripristinare il doppio provider.


# Pattern di errore LLM non transiente (quota/auth): un retry non li risolve.
# Derivati da errori reali visti in produzione (opencode-go 'Weekly usage limit
# reached. Resets in 3 days', 'AI_RetryError: Failed after 3 attempts', ...).
# Tenuti a livello modulo così sono testabili senza chiamare il modello.
OPENCODE_QUOTA_ERRORS = (
    "usage limit reached", "weekly usage limit", "resets in",
    "ai_retryerror", "ai_apicallerror", "failed after",
    "insufficient balance", "insufficient credit", "insufficient_quota",
    "rate_limit_error", "unauthorized", "invalid api key",
    "authentication failed", "permission_denied",
)


def _ask_opencode(prompt: str, as_json: bool = False, system: str | None = None):
    """LLM: opencode-go/glm-5.2 via `opencode run --format json`.
    Auth da XDG_DATA_HOME/opencode/auth.json (locale: ~/.local/share/opencode;
    cloud: scritto dal workflow da GH secret OPENCODE_GO_API_KEY).
    Output = stream JSONL; estrae i parti `text` dell'assistente.

    Robustezza: opencode, su errore di quota/auth del modello, NON esce da solo —
    ritenta e resta appeso fino al timeout (visto in produzione: 180s+ persi per
    ogni chiamata fallita). Con --print-logs --log-level ERROR gli errori di stream
    finiscono su stderr: un thread li legge in streaming e KILLA il processo non
    appena rileva un errore non transiente (quota/auth), così fail-fast in ~3s.
    Questi errori un retry non li risolve."""
    import re
    import subprocess
    import threading
    cmd = ["opencode", "run", "-m", "opencode-go/glm-5.2", "--format", "json",
           "--dangerously-skip-permissions", "--print-logs", "--log-level", "ERROR"]
    full = prompt
    if system:
        full = f"[ISTRUZIONI SISTEMA]\n{system}\n\n[/ISTRUZIONI SISTEMA]\n\n{prompt}"
    if as_json:
        full += "\n\nRispondi SOLO con JSON valido, niente markdown fence."
    # pattern di errore non transiente (quota/auth): un retry non li risolve.
    QUOTA = OPENCODE_QUOTA_ERRORS
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        raise RuntimeError("opencode non installato (setup opencode mancante / OPENCODE_GO_API_KEY non impostata)")
    try:
        proc.stdin.write(full)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    killed = {"reason": None}

    def watch_err() -> None:
        # drena stderr (evita deadlock buffer) e killa al primo errore non transiente
        try:
            for line in proc.stderr:
                low = line.lower()
                for p in QUOTA:
                    if p in low:
                        killed["reason"] = (p, line.strip()[:220])
                        proc.kill()
                        return
        except Exception:
            pass

    tw = threading.Thread(target=watch_err, daemon=True)
    tw.start()
    try:
        proc.wait(timeout=180)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise RuntimeError("opencode run timeout (180s): glm-5.2 non raggiungibile o appeso")
    tw.join(timeout=2)
    if killed["reason"]:
        p, msg = killed["reason"]
        raise RuntimeError(f"opencode-go/glm-5.2 non disponibile ({p}): {msg}")
    stdout = proc.stdout.read() if proc.stdout else ""
    if proc.returncode != 0:
        raise RuntimeError(f"opencode run fallito (exit {proc.returncode}): stdout={stdout[:300]}")
    text = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "text" and isinstance(ev.get("part"), dict):
            text += ev["part"].get("text", "")
    text = text.strip()
    if not text:
        raise RuntimeError(f"opencode run: nessun testo estratto. stdout={stdout[:300]}")
    text = _strip_fence(text)
    if as_json:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
        return json.loads(text)
    return text


def _ask(prompt: str, as_json: bool = False):
    """LLM call: opencode-go/glm-5.2 (consolidamento su singola key, 25/06).
    Trasparente per i chiamanti; robustezza fail-fast in _ask_opencode."""
    return _ask_opencode(prompt, as_json)


def signal_states(data: dict) -> dict:
    return {name: int(fn(data).iloc[-1]) for name, fn in SIGNALS.items()}


# Confluenza LUX 1.0: l'edge sistematico più robusto del desk, distillato per l'LLM.
LUX_CORE = ["tsmom", "liq_imbalance", "kronos_forecast"]   # devono concordare (top-conviction)
LUX_VOTE = LUX_CORE + ["smart_money_ratio", "oi_trend"]     # voto direzionale a 5


def lux_confluence(sig: dict) -> dict:
    """Stato confluenza LUX dai segnali correnti. aligned=True quando i 3 core
    (trend+liquidazioni+Kronos) sono tutti attivi E concordi → setup top-conviction."""
    core = [sig.get(n, 0) for n in LUX_CORE]
    aligned = all(v != 0 for v in core) and len({v > 0 for v in core}) == 1
    score = sum(sig.get(n, 0) for n in LUX_VOTE)
    return {"aligned": aligned,
            "direction": ("long" if core[0] > 0 else "short") if aligned else "—",
            "vote_score": score, "vote_n": len(LUX_VOTE),
            "components": {n: sig.get(n, 0) for n in LUX_VOTE}}


def build_context(symbols: list[str]) -> dict:
    assets = {}
    for s in symbols:
        d = fetch_live(s)
        c = d["candles"]
        oi = open_interest_24h(s) or {}
        fr = d["funding"].rate.iloc[-1] if d["funding"] is not None and len(d["funding"]) else 0.0
        ratio = ((d["flow"].taker_buy / d["flow"].volume.replace(0, np.nan)).tail(24).mean()
                 if d["flow"] is not None else 0.5)  # fallback HL: niente flow → neutro
        assets[s] = {
            "price": float(c.close.iloc[-1]),
            "atr_pct": round(float(atr_pct(c).iloc[-1]) * 100, 2),   # rumore tipico → stop floor
            "chg_24h": float(c.close.iloc[-1] / c.close.iloc[-25] - 1),
            "chg_7d": float(c.close.iloc[-1] / c.close.iloc[-169] - 1),
            "funding_8h": float(fr),
            "funding_apr": float(fr * 3 * 365),
            "taker_buy_ratio_24h": round(float(ratio), 4),
            "regime_7d": str(regimes(c).iloc[-1]),
            "signals": (_sig := signal_states(d)),
            "lux_confluence": lux_confluence(_sig),
            **{k: round(v, 4) if isinstance(v, float) else v for k, v in oi.items()},
        }
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "assets": assets,
        "news": news_headlines()[:25],
        "lessons": recall_lessons(symbols),
    }


def recall_lessons(symbols: list[str], k: int = 10) -> list[dict]:
    """Lezioni dal journal: prima quelle sugli stessi simboli, poi le più recenti."""
    path = ROOT / "paper/lessons.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    rows.sort(key=lambda r: (r.get("symbol") in symbols, r.get("logged_at", "")), reverse=True)
    return [{"symbol": r.get("symbol"), "verdict": r.get("verdict"),
             "lesson": r.get("lesson"), "tags": r.get("tags", [])} for r in rows[:k]]


def hard_check(p: dict, open_positions: int = 0, atr_by_symbol: dict | None = None) -> list[str]:
    """Strato 1: limiti deterministici. Una violazione = veto, l'LLM non può discutere."""
    errs = []
    if p.get("action") == "no_trade":
        return errs
    if float(p.get("leverage", 99)) > HARD_LIMITS["max_leverage"]:
        errs.append(f"leva {p.get('leverage')} > max {HARD_LIMITS['max_leverage']}")
    if float(p.get("risk_pct", 99)) > HARD_LIMITS["max_risk_per_trade_pct"]:
        errs.append(f"risk_pct {p.get('risk_pct')} > max {HARD_LIMITS['max_risk_per_trade_pct']}")
    lo, hi = HARD_LIMITS["stop_pct_range"]
    stop = float(p.get("stop_pct", 0))
    if not (lo <= stop <= hi):
        errs.append(f"stop_pct {p.get('stop_pct')} fuori range [{lo},{hi}] (stop obbligatorio)")
    # stop dentro il rumore (< 1 ATR) = noise-stop: causa #1 degli execution_issue
    atrp = (atr_by_symbol or {}).get(p.get("symbol"))
    if atrp and atrp > 0:
        floor = HARD_LIMITS["min_stop_atr_mult"] * atrp
        if stop < floor:
            errs.append(f"stop_pct {stop} < {HARD_LIMITS['min_stop_atr_mult']}*ATR ({floor:.2f}%): "
                        f"dentro il rumore, noise-stop")
    if open_positions >= HARD_LIMITS["max_concurrent_positions"]:
        errs.append("max posizioni concorrenti raggiunto")
    if p.get("direction") not in ("long", "short"):
        errs.append("direction mancante")
    if not p.get("thesis") or not p.get("invalidation"):
        errs.append("tesi o invalidazione mancante (obbligatorie)")
    return errs


def log_decision(record: dict) -> None:
    record["logged_at"] = datetime.now(timezone.utc).isoformat()
    DECISIONS.parent.mkdir(exist_ok=True)
    with DECISIONS.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def render_pack(ctx: dict) -> str:
    parts = [f"# Contesto mercato {ctx['ts']}\n## Asset\n{json.dumps(ctx['assets'], indent=1)}",
             "## News (timestampate)\n" + "\n".join(f"- [{n['ts'][:16]}] {n['title']}" for n in ctx["news"]),
             "## Lezioni dal journal\n" + ("\n".join(
                 f"- [{l['verdict']}] {l['symbol']}: {l['lesson']}" for l in ctx["lessons"]) or "(nessuna ancora)")]
    for role, prompt in ROLES.items():
        parts.append(f"\n=== RUOLO: {role.upper()} ===\n{prompt}")
    return "\n".join(parts)


def main() -> None:
    symbols = sys.argv[1].split(",")
    mode = sys.argv[2] if len(sys.argv) > 2 else "auto"

    if mode == "--check":
        proposal = json.loads(Path(sys.argv[3]).read_text())
        errs = hard_check(proposal)
        verdict = "hard_veto" if errs else "passed_hard_limits"
        print(f"{verdict}" + (f": {errs}" if errs else ""))
        log_decision({"stage": "hard_check", "proposal": proposal,
                      "verdict": verdict, "violations": errs})
        return

    ctx = build_context(symbols)
    if mode == "--pack":
        print(render_pack(ctx))
        return

    # full auto via glm-5.2 (opencode-go, consolidamento LLM 25/06)
    brief = _ask(f"{ROLES['analyst']}\n\nCONTESTO:\n{json.dumps(ctx, default=str)}")
    bull = _ask(f"{ROLES['bull']}\n\nBRIEF:\n{brief}")
    bear = _ask(f"{ROLES['bear']}\n\nBRIEF:\n{brief}")
    proposal = _ask(f"{ROLES['strategist']}\n\nBRIEF:\n{brief}\n\nBULL:\n{bull}\n\nBEAR:\n{bear}", as_json=True)
    atr_by_symbol = {s: a["atr_pct"] for s, a in ctx["assets"].items()}
    errs = hard_check(proposal, atr_by_symbol=atr_by_symbol)
    if errs:
        log_decision({"stage": "final", "proposal": proposal, "verdict": "hard_veto", "violations": errs})
        print(f"HARD VETO: {errs}")
        return
    risk = _ask(f"{ROLES['risk']}\n\nPROPOSTA:\n{json.dumps(proposal)}\n\nBRIEF:\n{brief}", as_json=True)
    log_decision({"stage": "final", "brief": brief, "bull": bull, "bear": bear,
                  "proposal": proposal, "risk": risk})
    print(json.dumps({"proposal": proposal, "risk": risk}, indent=1, default=str))


if __name__ == "__main__":
    main()
