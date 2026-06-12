"""Dashboard statica — la piattaforma "ricerca in pubblico" v1.

Genera dashboard/index.html dai journal: equity, posizioni, decisioni con tesi,
lezioni, lineage evolutivo. Zero processi residenti, pronta per Cloudflare Pages.
"""

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dashboard/index.html"

CSS = """
:root{--bg:#0b0e14;--card:#131722;--line:#222838;--txt:#dde3ee;--mut:#7d8590;
--green:#3fb950;--red:#f85149;--amber:#d29922;--blue:#58a6ff;--accent:#7c6df0}
*{box-sizing:border-box}body{font:15px/1.5 -apple-system,'Segoe UI',sans-serif;
background:var(--bg);color:var(--txt);margin:0;padding:0 0 4rem}
.wrap{max-width:1100px;margin:0 auto;padding:0 1.2rem}
header{position:sticky;top:0;background:rgba(11,14,20,.92);backdrop-filter:blur(8px);
border-bottom:1px solid var(--line);padding:.9rem 0;margin-bottom:1.6rem;z-index:9}
header .wrap{display:flex;justify-content:space-between;align-items:baseline}
h1{font-size:1.15rem;margin:0}h1 span{color:var(--accent)}
.ts{color:var(--mut);font-size:.8rem}
h2{font-size:1rem;margin:2rem 0 .8rem;color:var(--blue);text-transform:uppercase;
letter-spacing:.08em;font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1.1rem}
.card .k{color:var(--mut);font-size:.75rem;text-transform:uppercase;letter-spacing:.06em}
.card .v{font-size:1.6rem;font-weight:700;margin-top:.2rem}
.card .s{font-size:.8rem;color:var(--mut);margin-top:.3rem}
.pos .v{font-size:1.15rem}
table{border-collapse:collapse;width:100%;font-size:.83rem;background:var(--card);
border-radius:12px;overflow:hidden}
td,th{border-bottom:1px solid var(--line);padding:.55rem .7rem;text-align:left;vertical-align:top}
th{background:#1a1f2e;color:var(--mut);font-size:.72rem;text-transform:uppercase;letter-spacing:.05em}
tr:last-child td{border-bottom:none}
.up{color:var(--green)}.down{color:var(--red)}.muted{color:var(--mut)}
.badge{display:inline-block;padding:.1rem .55rem;border-radius:99px;font-size:.72rem;font-weight:600}
.b-green{background:#12261a;color:var(--green)}.b-red{background:#2d1416;color:var(--red)}
.b-amber{background:#2b2210;color:var(--amber)}.b-blue{background:#101c2e;color:var(--blue)}
.b-grey{background:#1c212e;color:var(--mut)}
.chart{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1rem;margin:.6rem 0}
.note{color:var(--mut);font-size:.8rem;margin:.4rem 0 0}
"""


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def badge(text: str, kind: str) -> str:
    return f"<span class='badge b-{kind}'>{html.escape(str(text))}</span>"


def fmt_px(v) -> str:
    try:
        return f"{float(v):,.4g}"
    except (TypeError, ValueError):
        return str(v)


def chart(points: list[tuple[str, float]], w: int = 1040, h: int = 200) -> str:
    if len(points) < 2:
        return "<div class='chart muted'>equity curve: in costruzione (servono più heartbeat)</div>"
    vals = [p[1] for p in points]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.15 or 1
    lo, hi = lo - pad, hi + pad
    xs = [40 + i * (w - 60) / (len(vals) - 1) for i in range(len(vals))]
    ys = [h - 24 - (v - lo) / (hi - lo) * (h - 44) for v in vals]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    color = "var(--green)" if vals[-1] >= vals[0] else "var(--red)"
    grid, labels = [], []
    for frac in (0, .5, 1):
        v = lo + (hi - lo) * frac
        y = h - 24 - frac * (h - 44)
        grid.append(f'<line x1="40" y1="{y:.0f}" x2="{w-20}" y2="{y:.0f}" stroke="#222838" stroke-width="1"/>')
        labels.append(f'<text x="36" y="{y+4:.0f}" fill="#7d8590" font-size="10" text-anchor="end">{v:,.0f}</text>')
    t0, t1 = points[0][0][:10], points[-1][0][:16]
    area = f'<polygon points="40,{h-24} {pts} {xs[-1]:.0f},{h-24}" fill="{color}" opacity="0.07"/>'
    return (f"<div class='chart'><svg viewBox='0 0 {w} {h}' width='100%'>"
            + "".join(grid) + area
            + f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>'
            + "".join(labels)
            + f'<text x="40" y="{h-6}" fill="#7d8590" font-size="10">{t0}</text>'
            + f'<text x="{w-20}" y="{h-6}" fill="#7d8590" font-size="10" text-anchor="end">{t1} UTC</text>'
            + "</svg></div>")


def table(rows: list[list[str]], cols: list[str]) -> str:
    if not rows:
        return "<p class='muted'>— ancora niente —</p>"
    head = "".join(f"<th>{c}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def pnl_cell(v) -> str:
    try:
        f = float(v)
        return f"<span class='{'up' if f >= 0 else 'down'}'>{f:+,.2f}$</span>"
    except (TypeError, ValueError):
        return ""


def main() -> None:
    state = json.loads((ROOT / "paper/state.json").read_text()) if (ROOT / "paper/state.json").exists() else {}
    journal = jsonl(ROOT / "paper/journal.jsonl")
    decisions = jsonl(ROOT / "paper/decisions.jsonl")
    lessons = jsonl(ROOT / "paper/lessons.jsonl")

    body = []

    # ── account cards + equity charts
    for sid, st in state.items():
        closes = [e for e in journal if e.get("type") == "close" and e.get("strategy") == sid]
        pnl = sum(e.get("pnl_usd", 0) for e in closes)
        wins = sum(1 for e in closes if e.get("pnl_usd", 0) > 0)
        beats = [(e["logged_at"], e["equity"]) for e in journal
                 if e.get("type") == "heartbeat" and e.get("strategy") == sid]
        npos = len(st.get("positions", {}))
        kind = "blue" if sid == "agents-v1" else "amber"
        body.append(f"<h2>{html.escape(sid)} {badge('agenti LLM' if sid == 'agents-v1' else 'challenger segnali', kind)}</h2>")
        body.append("<div class='cards'>"
                    f"<div class='card'><div class='k'>Equity (paper)</div><div class='v'>{st['equity']:,.2f}$</div>"
                    f"<div class='s'>start 10.000$ fittizi · prezzi reali</div></div>"
                    f"<div class='card'><div class='k'>P&L realizzato</div><div class='v'>{pnl_cell(pnl)}</div>"
                    f"<div class='s'>{len(closes)} trade chiusi · win {wins}/{len(closes) or 1}</div></div>"
                    f"<div class='card'><div class='k'>Posizioni aperte</div><div class='v'>{npos}</div>"
                    f"<div class='s'>{', '.join(st.get('positions', {})) or '—'}</div></div></div>")
        body.append(chart(beats))

        pos_rows = []
        for s, p in st.get("positions", {}).items():
            d = p.get("direction", "")
            pos_rows.append([html.escape(s), badge(d, "green" if d == "long" else "red"),
                             fmt_px(p.get("entry_px")), f"{p.get('size_usd', 0):,.0f}$",
                             fmt_px(p.get("stop_px")), fmt_px(p.get("target_px")),
                             f"<span class='muted'>{str(p.get('opened_at', ''))[:16]}</span>"])
        body.append("<h3>Posizioni aperte</h3>" if pos_rows else "")
        if pos_rows:
            body.append(table(pos_rows, ["asset", "lato", "entry", "size", "stop", "target", "aperta"]))
        if closes:
            cl_rows = [[str(e.get("ts", ""))[:16], html.escape(str(e.get("symbol"))),
                        badge(e.get("reason"), "grey"), fmt_px(e.get("exit_px")), pnl_cell(e.get("pnl_usd"))]
                       for e in closes[-8:][::-1]]
            body.append("<h3>Ultimi trade chiusi</h3>" + table(cl_rows, ["chiuso", "asset", "uscita", "prezzo", "p&l"]))

    # ── decisioni pipeline
    dec_rows = []
    for d in [d for d in decisions if d.get("stage") == "final"][-12:][::-1]:
        p, r = d.get("proposal", {}), d.get("risk", {})
        v = r.get("verdict", "")
        dec_rows.append([str(d.get("logged_at", ""))[:16], html.escape(str(p.get("symbol"))),
                         badge(p.get("direction"), "green" if p.get("direction") == "long" else "red"),
                         badge(v, "green" if v == "approve" else "amber" if v == "reduce" else "red"),
                         f"<div>{html.escape(str(p.get('thesis', ''))[:300])}</div>"
                         f"<div class='note'>invalidazione: {html.escape(str(p.get('invalidation', ''))[:160])}</div>"])
    body.append("<h2>Decisioni della pipeline {}</h2>".format(badge("tesi pubbliche", "blue"))
                + table(dec_rows, ["quando", "asset", "lato", "risk", "tesi"]))

    # ── lezioni
    les_rows = [[str(l.get("logged_at", ""))[:16], html.escape(str(l.get("symbol"))),
                 badge(l.get("verdict"), "red" if l.get("verdict") in ("thesis_wrong", "execution_issue") else "green"),
                 html.escape(str(l.get("lesson", "")))]
                for l in lessons[-12:][::-1]]
    body.append("<h2>Lezioni apprese {}</h2>".format(badge("reflection loop", "blue"))
                + table(les_rows, ["quando", "ambito", "verdetto", "lezione"]))

    # ── lineage
    lin_rows = []
    files = sorted(ROOT.glob("strategies/*.yaml")) + sorted(ROOT.glob("strategies/generated/*.yaml"))
    for f in files:
        if "candidates" in f.name:
            continue
        s = yaml.safe_load(f.read_text())
        bt = next(iter(s.get("backtest", {}).values()), {})
        agg = bt.get("aggregate") or bt.get("metrics") or {}
        sharpe = agg.get("mean_sharpe", agg.get("sharpe"))
        status = s.get("status", "?")
        lin_rows.append([html.escape(s["id"]), html.escape(str(s.get("parent") or "—")),
                         badge(status, {"champion": "green", "challenger": "amber"}.get(status, "grey")),
                         (f"<span class='{'up' if sharpe and sharpe > 0 else 'down'}'>{sharpe:.2f}</span>" if sharpe is not None else "—"),
                         f"<span class='muted'>{html.escape(str(s.get('evolution', {}).get('notes', ''))[:150])}</span>"])
    body.append("<h2>Evoluzione strategie {}</h2>".format(badge("lineage", "blue"))
                + table(lin_rows, ["strategia", "parent", "status", "sharpe", "mutazione"]))

    now = datetime.now(timezone.utc)
    page = (f"<!doctype html><html lang='it'><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>DeFi AI Vault — live research</title><style>{CSS}</style>"
            f"<header><div class='wrap'><h1><span>◆</span> DeFi AI Vault <span class='muted'>· ricerca in pubblico</span></h1>"
            f"<div class='ts'>aggiornato {now:%Y-%m-%d %H:%M} UTC · paper trading: balance fittizio, dati e prezzi reali</div></div></header>"
            f"<div class='wrap'>{''.join(body)}</div></html>")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page)
    print(f"dashboard → {OUT}")


if __name__ == "__main__":
    main()
