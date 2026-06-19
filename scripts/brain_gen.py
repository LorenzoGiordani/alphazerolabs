"""Brain generator — rende i dati operativi (JSONL/JSON/YAML) in un wiki
markdown stile Obsidian, versionato nel repo. NON è memoria runtime: serve a
umani e agenti-dev (Claude Code che legge il repo) per capire il "perché".

Sorgenti (sola lettura): paper/journal.jsonl, paper/lessons.jsonl,
paper/lifecycle.jsonl, paper/state.json, strategies/*.yaml.
Output (rigenerato ogni run, mai editato a mano): brain/.

Uso:  uv run scripts/brain_gen.py
"""

import json
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "paper"
STRAT = ROOT / "strategies"
BRAIN = ROOT / "brain"

# Definizioni stabili dei segnali (domain knowledge, scritte una volta).
# I segnali "in uso" sono rilevati dai yaml; quelli senza definizione finiscono
# in coda al glossario come TODO — così si nota subito un segnale nuovo.
GLOSSARY = {
    "funding_percentile": "Percentile del funding rate su lookback (es. 168h). Estremo = crowding di un lato del book; carburante per squeeze.",
    "range_breakout": "Rottura di un range multi-day con conferma di volume. Direzione = quella del breakout.",
    "taker_flow": "Sbilanciamento dei taker aggressivi (buy vs sell). Proxy di pressione direzionale intraday.",
    "vol_compression": "Volatilità schiacciata che precede un'espansione. Setup neutro: serve un regime/catalizzatore per diventare direzionale.",
    "vwap_zscore": "Distanza del prezzo dal VWAP in z-score. |z| basso (≤1σ) su altcoin high-beta = sotto soglia di edge (vedi lezioni).",
    "tsmom": "Time-series momentum: segno del rendimento su lookback. Base delle strategie trend-following.",
    "cot_percentile": "Percentile del posizionamento COT (Commitment of Traders) su future commodity. Estremi = crowding istituzionale.",
    "kronos_forecast": "Forecast del foundation model Kronos su serie OHLCV. Segnale predittivo, non reattivo.",
    "liq_imbalance": "Sbilanciamento delle liquidazioni (long vs short). Spike = potenziale cascata/squeeze.",
    "news_event": "Trigger event-driven da feed GDELT. Catalizzatore macro/narrativa, non tecnico.",
    "oi_trend": "Trend dell'open interest. OI fermo su prezzo che sale = short non capitolati (carburante squeeze).",
    "smart_money_ratio": "Rapporto posizionamento large vs retail. Proxy di flusso informato.",
}


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def load() -> dict:
    journal = read_jsonl(PAPER / "journal.jsonl")
    lessons = read_jsonl(PAPER / "lessons.jsonl")
    lifecycle = read_jsonl(PAPER / "lifecycle.jsonl")
    state = json.loads((PAPER / "state.json").read_text()) if (PAPER / "state.json").exists() else {}
    specs = {}
    for y in sorted([*STRAT.glob("*.yaml"), *(STRAT / "generated").glob("*.yaml")]):
        # gestisce single-doc, multi-doc (--- separator) e liste di candidati
        for doc in yaml.safe_load_all(y.read_text()):
            for d in doc if isinstance(doc, list) else [doc]:
                if isinstance(d, dict) and d.get("id") and d["id"] not in specs:
                    specs[d["id"]] = d
    return dict(journal=journal, lessons=lessons, lifecycle=lifecycle, state=state, specs=specs)


def all_strategies(data: dict) -> list[str]:
    # strategie con attività reale: stato live, journal o lezioni
    names = set(data["state"])
    for j in data["journal"]:
        if j.get("strategy"):
            names.add(j["strategy"])
    for l in data["lessons"]:
        if l.get("strategy"):
            names.add(l["strategy"])
    # + spec non-candidate (candidate evolutivi e scratch tmp-* restano fuori)
    for sid, spec in data["specs"].items():
        if spec.get("status") != "candidate" and not sid.startswith("tmp-"):
            names.add(sid)
    return sorted(names)


def stats_for(strat: str, data: dict) -> dict:
    closes = [j for j in data["journal"] if j.get("strategy") == strat and j.get("type") == "close"]
    opens = [j for j in data["journal"] if j.get("strategy") == strat and j.get("type") == "open"]
    pnls = [c.get("pnl_usd", 0.0) for c in closes]
    wins = [p for p in pnls if p > 0]
    eq = data["state"].get(strat, {}).get("equity")
    open_now = len(data["state"].get(strat, {}).get("positions", {}))
    return dict(
        n_open=len(opens), n_closed=len(closes), open_now=open_now,
        total_pnl=sum(pnls), win_rate=(len(wins) / len(pnls)) if pnls else 0.0,
        equity=eq, closes=closes, opens=opens,
    )


def fmt_usd(v) -> str:
    return "—" if v is None else f"${v:,.2f}"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


# ---------- pagine ----------

def page_strategy(strat: str, data: dict) -> str:
    spec = data["specs"].get(strat, {})
    st = stats_for(strat, data)
    lessons = [l for l in data["lessons"] if l.get("strategy") == strat]
    events = [e for e in data["lifecycle"] if e.get("strategy") == strat]
    status = spec.get("status") or ("retired" if any(e.get("event") == "retire" for e in events) else "live")

    L = [f"# {strat}", "", "[[README|← Brain index]]", ""]
    L += ["## Anagrafica", "", f"- **status**: {status}"]
    if spec.get("parent"):
        L.append(f"- **parent**: [[{spec['parent']}]]")
    if spec.get("created"):
        L.append(f"- **created**: {spec['created']}")
    fam = next((e.get("family") for e in events if e.get("family")), None)
    if fam:
        L.append(f"- **family**: {fam}")
    if not spec:
        L.append("- _nessuno spec YAML: pagina da dati runtime_")
    L.append("")

    if spec.get("thesis"):
        L += ["## Tesi", "", spec["thesis"].strip(), ""]
    if spec.get("evolution", {}).get("notes"):
        L += ["## Note evoluzione", "", str(spec["evolution"]["notes"]).strip(), ""]

    L += ["## Performance (paper)", "",
          f"- equity: {fmt_usd(st['equity'])}",
          f"- trade chiusi: {st['n_closed']} · win rate: {st['win_rate']*100:.0f}%",
          f"- PnL totale: {fmt_usd(st['total_pnl'])}",
          f"- posizioni aperte ora: {st['open_now']}", ""]

    pos = data["state"].get(strat, {}).get("positions", {})
    if pos:
        L += ["### Posizioni aperte", "", "| symbol | dir | entry | stop | target | size |", "|---|---|---|---|---|---|"]
        for sym, p in pos.items():
            L.append(f"| {sym} | {p.get('direction','')} | {p.get('entry_px','')} | "
                     f"{p.get('stop_px','')} | {p.get('target_px','')} | {fmt_usd(p.get('size_usd'))} |")
        L.append("")

    if st["closes"]:
        L += ["### Trade chiusi", "", "| symbol | reason | exit | PnL |", "|---|---|---|---|"]
        for c in st["closes"]:
            L.append(f"| {c.get('symbol','')} | {c.get('reason','')} | {c.get('exit_px','')} | {fmt_usd(c.get('pnl_usd'))} |")
        L.append("")

    if lessons:
        L += ["## Lezioni", ""]
        for l in lessons:
            tags = " ".join(f"#{t}" for t in l.get("tags", []))
            L.append(f"- **{l.get('verdict','')}** ({l.get('symbol','')}, {fmt_usd(l.get('pnl_usd'))}): "
                     f"{l.get('lesson','').strip()} {tags}".rstrip())
        L.append("")

    if events:
        L += ["## Eventi lifecycle", ""]
        for e in events:
            L.append(f"- **{e.get('event','')}** ({e.get('logged_at','')[:10]}): {e.get('reason','')}")
        L.append("")

    L.append("[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]")
    return "\n".join(L)


def page_index(data: dict, strats: list[str]) -> str:
    L = ["# Brain — DeFi AI Vault", "",
         "_Wiki auto-generato da `scripts/brain_gen.py`. Non editare a mano: "
         "rigenerato a ogni paper run dai dati in `paper/`._", "",
         "Pagine: [[lessons]] · [[timeline]] · [[glossary]]", "",
         "## Strategie", "",
         "| strategia | status | equity | chiusi | win% | PnL | aperte |",
         "|---|---|---|---|---|---|---|"]
    for s in strats:
        spec = data["specs"].get(s, {})
        st = stats_for(s, data)
        retired = any(e.get("event") == "retire" and e.get("strategy") == s for e in data["lifecycle"])
        status = spec.get("status") or ("retired" if retired else "live")
        L.append(f"| [[{s}]] | {status} | {fmt_usd(st['equity'])} | {st['n_closed']} | "
                 f"{st['win_rate']*100:.0f}% | {fmt_usd(st['total_pnl'])} | {st['open_now']} |")
    L.append("")
    return "\n".join(L)


def page_lessons(data: dict) -> str:
    by_tag = defaultdict(list)
    for l in data["lessons"]:
        for t in (l.get("tags") or ["untagged"]):
            by_tag[t].append(l)
    L = ["# Lezioni", "", "[[README|← Brain index]]", "",
         f"_{len(data['lessons'])} lezioni, clusterizzate per tag._", ""]
    for tag in sorted(by_tag):
        L += [f"## #{tag}", ""]
        for l in by_tag[tag]:
            L.append(f"- [[{l.get('strategy','')}]] · **{l.get('verdict','')}** "
                     f"({l.get('symbol','')}): {l.get('lesson','').strip()}")
        L.append("")
    return "\n".join(L)


def page_timeline(data: dict) -> str:
    rows = []
    for e in data["lifecycle"]:
        rows.append((e.get("logged_at", ""), f"🔄 lifecycle **{e.get('event','')}** [[{e.get('strategy','')}]] — {e.get('reason','')}"))
    for d in data["journal"]:
        if d.get("type") in ("open", "close"):
            ts = d.get("logged_at", "")
            if d["type"] == "open":
                rows.append((ts, f"🟢 open [[{d.get('strategy','')}]] {d.get('symbol','')} {d.get('direction','')}"))
            else:
                rows.append((ts, f"🔴 close [[{d.get('strategy','')}]] {d.get('symbol','')} — {d.get('reason','')} {fmt_usd(d.get('pnl_usd'))}"))
    rows.sort(reverse=True)
    L = ["# Timeline", "", "[[README|← Brain index]]", "",
         "_Eventi lifecycle + open/close, più recenti in alto._", ""]
    for ts, txt in rows:
        L.append(f"- `{ts[:19]}` {txt}")
    L.append("")
    return "\n".join(L)


def page_glossary(data: dict) -> str:
    # quali segnali compaiono nei yaml e in quali strategie
    used: dict[str, list[str]] = defaultdict(list)
    for sid, spec in data["specs"].items():
        for sig in spec.get("signals", []) or []:
            if isinstance(sig, dict) and sig.get("name"):
                used[sig["name"]].append(sid)
    L = ["# Glossario segnali", "", "[[README|← Brain index]]", "",
         "_Definizioni stabili in `scripts/brain_gen.py` (GLOSSARY). "
         "Colonna 'in uso' = strategie YAML che montano il segnale._", "",
         "| segnale | definizione | in uso |", "|---|---|---|"]
    for name in sorted(set(GLOSSARY) | set(used)):
        definition = GLOSSARY.get(name, "**TODO: definire** (segnale nuovo, non in glossario)")
        strats = " ".join(f"[[{s}]]" for s in sorted(used.get(name, []))) or "—"
        L.append(f"| `{name}` | {definition} | {strats} |")
    L.append("")
    return "\n".join(L)


def main() -> None:
    data = load()
    strats = all_strategies(data)
    write(BRAIN / "README.md", page_index(data, strats))
    write(BRAIN / "lessons.md", page_lessons(data))
    write(BRAIN / "timeline.md", page_timeline(data))
    write(BRAIN / "glossary.md", page_glossary(data))
    for s in strats:
        write(BRAIN / f"{s}.md", page_strategy(s, data))
    print(f"brain: {len(strats)} strategie + index/lessons/timeline → {BRAIN}")


if __name__ == "__main__":
    main()
