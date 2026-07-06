"""Evoluzione delle strategie engine:portfolio (xsmom, highvol, tsmom-neutral…).

I champion veri del sistema vivono qui — prima di questo modulo il loop
evolutivo copriva solo le strategie meccaniche a segnali. Mutazioni SOLO sul
blocco `portfolio` (registry chiuso di knob, cfr. PORTFOLIO_REGISTRY_DOC):
universe/risk/engine sono forzati dal parent, come il blocco risk in evolve.py.

Eval offline: replica dei fattori live di portfolio_paper.py (xsmom single e
multi-orizzonte, tsmom sign, highvol, combo z-scored) su panel di chiusure da
data/candles/, con costo sul turnover e overlay vol-target Moreira-Muir.
liqimb ESCLUSO dall'evoluzione: il collector coinalyze ha copertura parziale,
un backtest offline mentirebbe.

Stessa filosofia di evolve_auto: backtest = sanity (sharpe>0) + baseline,
il gate vero è il paper forward. Chi passa → `challenger`, portfolio_all.py
lo prende in carico al run successivo.

Uso: .venv/bin/python scripts/evolve_portfolio.py [--n 4] [--months 6]
(il cron giornaliero passa da evolve_auto.py, che chiama evolve_portfolio_family)
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.engine import DEFAULT_SLIPPAGE, HL_TAKER_FEE
from backtest.lifecycle import all_specs, family, paper_stats
from backtest.portfolio import sign_weights, xs_momentum_weights
from backtest.stats import deflated_sharpe
from scripts.evolve import OUT_DIR, ask_glm, lessons_block

COST = HL_TAKER_FEE + DEFAULT_SLIPPAGE
PPY = 24 * 365                     # panel orario
MAX_FAMILY_CHALLENGERS = 6         # stesso cap di evolve_auto

EVOLVABLE_FACTORS = ("xsmom", "tsmom", "highvol")

PORTFOLIO_REGISTRY_DOC = """Knob mutabili del blocco `portfolio` (REGISTRY CHIUSO — solo questi, solo questi range):
- factor: xsmom | tsmom | highvol  (liqimb NON mutabile: dati offline parziali)
- factors: [xsmom, highvol] + weights: [w1, w2]  → combo multi-fattore z-scored (somma pesi = 1)
- lookback_h (24-720): orizzonte del ritorno trailing (xsmom/tsmom/combo)
- lookbacks_h: lista di orizzonti (SOLO xsmom, es. [96,168,336]) → media dei trailing per asset
- vol_lookback_h (24-336): finestra std oraria per highvol/combo
- rebalance_h (4-336): frequenza ribilanciamento (basso = più turnover = più fee)
- long_q (0.5-0.9) / short_q (0.1-0.5): quantili delle gambe, long_q > short_q (non tsmom)
- gross (0.3-1.5): leva lorda del book
- dollar_neutral: true/false (non tsmom; false = solo gamba long)
- vol_target: {enabled: true, target_vol_ann: 0.1-0.5, vol_window_h: 240-1440, gross_floor: 0.2-0.6, gross_cap: 1.0-2.0}
  overlay Moreira-Muir: scala il gross inverso alla vol realizzata del book.
NON mutare: universe, paper_symbols, risk, engine, timeframe (forzati dal parent).
Proponi nel campo `yaml` SOLO: portfolio (blocco completo mutato) + thesis (perché la mutazione dovrebbe battere il parent)."""


# ---------------------------------------------------------------- eval offline

def panel(symbols: list[str], months: int) -> pd.DataFrame:
    """Panel chiusure orarie (index ts, colonne simboli): parquet locale se c'è,
    altrimenti fetch live con cache (runner cloud: data/candles è gitignorata —
    stesso pattern di backtest_report._load_candles). Simboli irrecuperabili saltati."""
    cols = {}
    for s in symbols:
        p = ROOT / f"data/candles/{s}.parquet"
        if p.exists():
            c = pd.read_parquet(p)
        else:
            try:
                from pipeline.live import fetch_live_cached
                c = fetch_live_cached(s, lookback_h=5000)["candles"]
            except Exception as e:
                print(f"  panel {s}: fetch fallito ({e})", file=sys.stderr)
                continue
        cols[s] = c.tail(months * 30 * 24).set_index("ts")["close"]
    df = pd.DataFrame(cols).sort_index()
    return df[~df.index.duplicated()]


def _signal_panel(pf: dict, px: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """DataFrame segnale per-timestamp secondo il fattore (specchio di
    portfolio_paper.py) + warmup necessario. Anti-lookahead: solo dati ≤ t."""
    factors = pf.get("factors")
    factor = pf.get("factor", "xsmom")
    lb = int(pf.get("lookback_h", 168))
    vol_lb = int(pf.get("vol_lookback_h", 72))
    if factors:                                  # combo z-scored (come combo_signal live)
        parts, warm = [], 0
        for f, w in zip(factors, pf.get("weights", [0.5, 0.5])):
            if f == "xsmom":
                sig, warm = px.pct_change(lb), max(warm, lb)
            elif f == "highvol":
                sig = px.pct_change().rolling(vol_lb).std()
                warm = max(warm, vol_lb)
            else:
                raise ValueError(f"fattore combo fuori registry: {f}")
            z = sig.sub(sig.mean(axis=1), axis=0).div(sig.std(axis=1).replace(0, np.nan), axis=0)
            parts.append(z * float(w))
        return sum(parts), warm
    if factor == "highvol":
        return px.pct_change().rolling(vol_lb).std(), vol_lb
    multi = pf.get("lookbacks_h")
    if multi:                                    # media trailing multi-orizzonte (xsmom)
        sig = sum(px.pct_change(int(h)) for h in multi) / len(multi)
        return sig, max(int(h) for h in multi)
    return px.pct_change(lb), lb                 # xsmom/tsmom single


def _weight_fn(pf: dict):
    if pf.get("factor") == "tsmom":
        return lambda row, g: sign_weights(row, gross=g)
    return lambda row, g: xs_momentum_weights(
        row, long_q=float(pf.get("long_q", 0.66)), short_q=float(pf.get("short_q", 0.33)),
        gross=g, dollar_neutral=bool(pf.get("dollar_neutral", True)))


def run_portfolio(px: pd.DataFrame, pf: dict) -> tuple[pd.Series, pd.Series, dict]:
    """Loop ribilanciamento con costo sul turnover e vol-target opzionale.
    Iterativo (non vettoriale) perché il vol-target legge l'equity PASSATA del
    book — anti-lookahead: pesi decisi a t applicati dal bar successivo."""
    sig, warmup = _signal_panel(pf, px)
    ret = px.pct_change().fillna(0.0).to_numpy()
    n = len(px)
    rebalance_h = int(pf["rebalance_h"])
    gross = float(pf.get("gross", 1.0))
    vt = pf.get("vol_target") or {}
    wfn = _weight_fn(pf)

    last_w = np.zeros(px.shape[1])
    port_r = np.zeros(n)
    rebalances = 0
    for i in range(warmup, n):
        port_r[i] = float(last_w @ ret[i])
        if (i - warmup) % rebalance_h == 0:
            g = gross
            if vt.get("enabled"):
                win = int(vt.get("vol_window_h", 720))
                past = port_r[max(warmup, i - win):i]
                if len(past) >= 30 and past.std() > 0:
                    m = float(vt.get("target_vol_ann", 0.20)) / (past.std() * np.sqrt(PPY))
                    g = gross * float(np.clip(m, float(vt.get("gross_floor", 0.3)),
                                              float(vt.get("gross_cap", 1.5))))
            w = wfn(sig.iloc[i], g).reindex(px.columns).fillna(0.0).to_numpy()
            port_r[i] -= float(np.abs(w - last_w).sum()) * COST
            last_w = w
            rebalances += 1
    rets = pd.Series(port_r, index=px.index)
    equity = (1.0 + rets).cumprod()
    return equity, rets, {"rebalances": rebalances}


def eval_portfolio(spec: dict, px: pd.DataFrame, months: int) -> tuple[dict, pd.Series]:
    equity, rets, meta = run_portfolio(px, spec["portfolio"])
    sharpe = float(rets.mean() / rets.std() * np.sqrt(PPY)) if rets.std() else 0.0
    agg = {"total_return": round(float(equity.iloc[-1] - 1), 4),
           "sharpe": round(sharpe, 2),
           "max_drawdown": round(float((equity / equity.cummax() - 1).min()), 4),
           "rebalances": meta["rebalances"]}
    return agg, rets.loc[rets != 0]


# ---------------------------------------------------------------- validazione

_RANGES = {"lookback_h": (24, 720), "vol_lookback_h": (24, 336),
           "rebalance_h": (4, 336), "long_q": (0.5, 0.9), "short_q": (0.1, 0.5),
           "gross": (0.3, 1.5)}
_ALLOWED_KEYS = set(_RANGES) | {"factor", "factors", "weights", "lookbacks_h",
                                "dollar_neutral", "vol_target"}


def validate_portfolio(cand: dict, parent: dict, idx: int) -> dict:
    """Mutazione = SOLO blocco portfolio + thesis; tutto il resto dal parent."""
    pf = cand.get("portfolio")
    if not isinstance(pf, dict):
        raise ValueError("mutazione senza blocco portfolio")
    extra = set(pf) - _ALLOWED_KEYS
    if extra:
        raise ValueError(f"knob fuori registry: {sorted(extra)}")
    factors = pf.get("factors")
    if factors:
        if not set(factors) <= {"xsmom", "highvol"}:
            raise ValueError(f"combo fuori registry: {factors}")
        ws = pf.get("weights", [])
        if len(ws) != len(factors) or abs(sum(ws) - 1.0) > 0.01:
            raise ValueError(f"weights incoerenti coi factors: {ws}")
    elif pf.get("factor", "xsmom") not in EVOLVABLE_FACTORS:
        raise ValueError(f"factor fuori registry: {pf.get('factor')}")
    for k, (lo, hi) in _RANGES.items():
        if k in pf and not (lo <= float(pf[k]) <= hi):
            raise ValueError(f"{k} fuori range [{lo},{hi}]: {pf[k]}")
    for h in pf.get("lookbacks_h", []):
        if not (24 <= int(h) <= 720):
            raise ValueError(f"lookbacks_h fuori range: {h}")
    if float(pf.get("long_q", 0.66)) <= float(pf.get("short_q", 0.33)):
        raise ValueError("long_q deve superare short_q")

    from datetime import date
    spec = {k: parent[k] for k in ("engine", "universe", "paper_symbols", "timeframe",
                                   "decision_every_h", "signals", "exit", "risk")
            if k in parent}
    spec["portfolio"] = pf
    spec["thesis"] = cand.get("thesis", "")
    spec["parent"] = parent["id"]
    spec["created"] = str(date.today())
    spec["id"] = f"{parent['id'].rsplit('-v', 1)[0]}-g{idx}-{date.today():%y%m%d}"
    return spec


# ---------------------------------------------------------------- loop famiglia

def pick_portfolio_parents() -> dict:
    """Un parent per famiglia portfolio: champion, o miglior challenger per
    basket_sharpe_r paper (le liqimb saltate: fattore non evolvibile offline)."""
    by_fam: dict[str, list] = {}
    for f, s in all_specs():
        if s.get("engine") != "portfolio" or s.get("status") not in ("champion", "challenger"):
            continue
        pf = s.get("portfolio", {})
        factor_ok = (pf.get("factors") or pf.get("factor", "xsmom")) != "liqimb"
        if factor_ok:
            by_fam.setdefault(family(s["id"]), []).append((f, s))
    parents = {}
    for fam, members in by_fam.items():
        champ = next((m for m in members if m[1]["status"] == "champion"), None)
        parents[fam] = champ or max(
            members, key=lambda m: paper_stats(m[1]["id"]).get("basket_sharpe_r", 0.0))
    return parents


def evolve_portfolio_family(parent_path: Path, parent: dict, n: int, months: int) -> int:
    fam = family(parent["id"])
    n_challengers = len([1 for _, s in all_specs()
                         if family(s["id"]) == fam and s.get("status") == "challenger"
                         and s.get("engine") == "portfolio"])
    if n_challengers >= MAX_FAMILY_CHALLENGERS:
        print(f"\n[{fam}] piena ({n_challengers} challenger ≥ cap {MAX_FAMILY_CHALLENGERS}): "
              f"generazione sospesa finché promote non fa spazio")
        return 0

    symbols = [s for s in str(parent.get("paper_symbols", "")).split(",") if s]
    px = panel(symbols, months)
    if px.shape[1] < 3 or len(px) < 30 * 24:
        print(f"\n[{fam}] panel insufficiente ({px.shape}): skip", file=sys.stderr)
        return 0
    pa, _ = eval_portfolio(parent, px, months)
    print(f"\n[{fam}] parent {parent['id']} (portfolio): sharpe {pa['sharpe']:.2f}, "
          f"ret {pa['total_return']:+.2%}, maxDD {pa['max_drawdown']:.2%}")

    prompt = f"""{PORTFOLIO_REGISTRY_DOC}

PARENT (YAML):
{parent_path.read_text()}

RISULTATI PARENT su basket {','.join(px.columns)}, {months} mesi (fee/slippage sul turnover inclusi):
{json.dumps(pa)}
{lessons_block(fam)}

Proponi {n} mutazioni del blocco `portfolio` (+ thesis). Obiettivo: Sharpe robusto
con drawdown contenuto, non picchi di ritorno. Il turnover costa: rebalance più
frequente deve guadagnarsi le fee."""
    try:
        specs = [yaml.safe_load(c["yaml"]) for c in ask_glm(prompt)["candidates"]]
    except Exception as e:
        print(f"  generazione LLM fallita: {e}", file=sys.stderr)
        return 0

    rows = []
    for i, cand in enumerate(specs, 1):
        try:
            spec = validate_portfolio(cand, parent, i)
            agg, rets = eval_portfolio(spec, px, months)
            spec["backtest"] = {f"basket_{months}m": {"aggregate": agg}}
            rows.append((spec, agg, rets))
        except Exception as e:
            print(f"  candidato {i} scartato: {e}", file=sys.stderr)
    if not rows:
        return 0

    n_prior = len([f for f in OUT_DIR.glob("*.yaml") if "candidates" not in f.name])
    trial_srs = [agg["sharpe"] / np.sqrt(PPY) for _, agg, _ in rows]  # SR per-periodo
    promoted = 0
    for spec, agg, rets in rows:
        d = deflated_sharpe(rets, n_prior + len(rows) + 1, trial_srs)
        agg["dsr"] = round(d["dsr"], 3)          # informativo, come in evolve_auto
        passes = agg["sharpe"] > 0
        spec["status"] = "challenger" if passes else "candidate"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / f"{spec['id']}.yaml").write_text(
            yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
        flag = "✓ CHALLENGER (in paper dal prossimo run)" if passes else "· candidate (backtest ≤ 0)"
        print(f"  {spec['id']:<44} DSR {agg['dsr']:.2f} | sharpe {agg['sharpe']:+.2f} "
              f"| DD {agg['max_drawdown']:.1%} | {flag}")
        promoted += int(passes)
    return promoted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--months", type=int, default=6)
    args = ap.parse_args()
    parents = pick_portfolio_parents()
    if not parents:
        print("nessuna famiglia portfolio attiva evolvibile")
        return
    total = 0
    for fam, (pf, ps) in parents.items():
        total += evolve_portfolio_family(pf, ps, args.n, args.months)
    print(f"\n{total} nuovi challenger portfolio in paper")


if __name__ == "__main__":
    main()
