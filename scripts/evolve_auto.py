"""Loop evolutivo AUTOMATICO: per ogni famiglia, evolve il miglior esemplare.

Copre TRE canali (tutti giornalieri tranne i seed):
  A. famiglie MECCANICHE (engine a segnali) — mutazioni via evolve.validate
  B. famiglie PORTFOLIO (engine:portfolio) — mutazioni del blocco portfolio
     via scripts/evolve_portfolio.py (i champion veri vivono lì)
  C. SEED settimanali (lunedì): strategie nuove dal registry, non figlie di
     nessuno — sangue fresco contro gli ottimi locali del ceppo
I prompt includono le LEZIONI del paper (perché le sorelle sono morte):
l'evoluzione impara dal forward, non solo dal backtest.

Per ogni ceppo attivo (champion, o miglior challenger se non c'è champion):
  1. LLM genera N mutazioni (registry chiuso di segnali)
  2. ognuna valutata sul basket → backtest = SOLO sanity check + baseline
  3. chi ha expectancy positiva (mean_sharpe > 0) → `challenger` SUBITO in paper:
     il paper trading è il gate vero (FORMAT.md: mai promuovere/scartare su
     backtest) — i dati forward si raccolgono dal primo giorno
  4. le mutazioni con backtest negativo → `candidate` (archiviate, visibili)

Anti-flood: famiglia già piena di challenger (cap) → generazione sospesa finché
promote.py non fa spazio (retire perdenti/zombie). Così il paper loop resta
leggibile e il numero di strategie attive è bounded.

Se non c'è NESSUN ceppo meccanico attivo (successo lug 2026: promote ha ritirato
l'ultima meccanica e il loop si è spento in silenzio), riparte dalle migliori
`candidate` per sharpe di backtest — l'evoluzione non deve mai morire.

Pensato per il cron GIORNALIERO (00:xx UTC). LLM via ask_glm (vedi scripts/evolve.py).
Uso: .venv/bin/python scripts/evolve_auto.py [--n 4] [--months 6]
Exit 1 se non trova nulla da evolvere: lo step Actions diventa rosso invece di
morire muto (lezione: ImportError silenziato da `|| true` per settimane).
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.lifecycle import (DEFAULT_SYMBOLS, NON_MECHANICAL_ENGINES,
                                active_specs, all_specs, family, paper_stats,
                                paper_symbols)
from backtest.stats import deflated_sharpe, sharpe_moments
from scripts.evolve import (EXIT_DOC, OUT_DIR, REGISTRY_DOC, ask_glm,
                            eval_basket, lessons_block, load_data, validate)
from scripts.evolve_portfolio import evolve_portfolio_family, pick_portfolio_parents

MAX_FAMILY_CHALLENGERS = 6   # cap challenger per famiglia: oltre, si aspetta promote
MAX_RESEED_FAMILIES = 2      # famiglie riseminate per run quando il loop è spento
MAX_MECH_FAMILIES = 8        # cap famiglie meccaniche attive: oltre, niente seed nuovi
N_SEEDS = 2                  # strategie NUOVE chieste all'LLM il lunedì

# blocco risk per i seed (non hanno parent da cui ereditarlo): conservativo,
# promote alza la posta solo con evidenza forward
DEFAULT_SEED_RISK = {"max_leverage": 1.5, "risk_per_trade_pct": 1.0,
                     "max_concurrent_positions": 4}


def _bt_sharpe(spec: dict) -> float:
    bt = next(iter(spec.get("backtest", {}).values()), {})
    return bt.get("aggregate", {}).get("mean_sharpe", float("-inf"))


def pick_parents() -> dict:
    """Un parent per famiglia: il champion, o il miglior challenger per sharpe_r.
    Loop spento (zero meccaniche attive) → riseed dalle migliori candidate."""
    by_fam: dict[str, list] = {}
    for f, s in active_specs():
        by_fam.setdefault(family(s["id"]), []).append((f, s))
    parents = {}
    for fam, members in by_fam.items():
        champ = next((m for m in members if m[1]["status"] == "champion"), None)
        if champ:
            parents[fam] = champ
        else:
            parents[fam] = max(members, key=lambda m: paper_stats(m[1]["id"])["sharpe_r"])
    if parents:
        return parents

    print("nessun ceppo attivo: riseed dalle migliori candidate (backtest sharpe)")
    best_by_fam: dict[str, tuple] = {}
    for f, s in all_specs():
        if s.get("status") != "candidate" or s.get("engine") in NON_MECHANICAL_ENGINES:
            continue
        if _bt_sharpe(s) == float("-inf"):
            continue  # candidate senza backtest: niente baseline da cui mutare
        fam = family(s["id"])
        if fam not in best_by_fam or _bt_sharpe(s) > _bt_sharpe(best_by_fam[fam][1]):
            best_by_fam[fam] = (f, s)
    ranked = sorted(best_by_fam.items(), key=lambda kv: _bt_sharpe(kv[1][1]), reverse=True)
    return dict(ranked[:MAX_RESEED_FAMILIES])


def evolve_family(parent_path: Path, parent: dict, n: int, months: int) -> int:
    fam = family(parent["id"])
    n_challengers = len([1 for _, s in all_specs()
                         if family(s["id"]) == fam and s.get("status") == "challenger"
                         and s.get("engine") not in NON_MECHANICAL_ENGINES])
    if n_challengers >= MAX_FAMILY_CHALLENGERS:
        print(f"\n[{fam}] piena ({n_challengers} challenger ≥ cap {MAX_FAMILY_CHALLENGERS}): "
              f"generazione sospesa finché promote non fa spazio")
        return 0

    symbols = paper_symbols(parent).split(",")
    datasets = {s: load_data(s, months) for s in symbols}
    pe = eval_basket(parent, datasets)
    pa = pe["aggregate"]
    print(f"\n[{fam}] parent {parent['id']}: "
          f"mean_sharpe {pa['mean_sharpe']:.2f}, mean_ret {pa['mean_return']:+.2%}")

    prompt = f"""{REGISTRY_DOC}

PARENT (YAML):
{parent_path.read_text()}

RISULTATI PARENT su basket {','.join(symbols)}, {months} mesi (fee/slippage/funding inclusi):
aggregato: {pa}
{lessons_block(fam)}

Proponi {n} mutazioni in YAML (schema identico al parent). Obiettivo: robustezza
sul basket, non picchi su singolo asset. Puoi usare `entry.veto` (segnali-gate
che sospendono entrate, es. news_event come filtro di volatilità)."""
    try:
        specs = [yaml.safe_load(c["yaml"]) for c in ask_glm(prompt)["candidates"]]
    except Exception as e:
        print(f"  generazione LLM fallita: {e}", file=sys.stderr)
        return 0

    rows = []
    for i, cand in enumerate(specs, 1):
        try:
            spec = validate(cand, parent, i)
            res = eval_basket(spec, datasets)
            rets = res.pop("basket_rets")
            spec["backtest"] = {f"basket_{months}m": res}
            rows.append((spec, res["aggregate"], rets))
        except Exception as e:
            print(f"  candidato {i} scartato: {e}", file=sys.stderr)

    if not rows:
        return 0
    n_prior = len([f for f in OUT_DIR.glob("*.yaml") if "candidates" not in f.name])
    trial_srs = [sharpe_moments(r)["sr"] for _, _, r in rows]
    k = n_prior + len(rows) + 1

    promoted = 0
    for spec, agg, rets in rows:
        d = deflated_sharpe(rets, k, trial_srs)
        agg["dsr"] = round(d["dsr"], 3)  # informativo: promote lo usa come gate soft al titolo
        agg["dsr_sr0_ann"] = d["sr0_ann"]
        # gate = solo sanity: expectancy positiva sul basket. Il test vero è il
        # paper forward (dati out-of-sample dal primo giorno) — promote.py decide lì.
        passes = agg["mean_sharpe"] > 0
        spec["status"] = "challenger" if passes else "candidate"
        if passes:
            spec.setdefault("paper_symbols", ",".join(symbols))
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / f"{spec['id']}.yaml").write_text(
            yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
        flag = "✓ CHALLENGER (in paper dal prossimo run)" if passes else "· candidate (backtest ≤ 0)"
        print(f"  {spec['id']:<40} DSR {agg['dsr']:.2f} | sharpe {agg['mean_sharpe']:+.2f} | {flag}")
        promoted += int(passes)
    return promoted


def seed_new_families(months: int) -> int:
    """SEED settimanale (lunedì): strategie NUOVE dal registry segnali, non figlie
    di nessuno — per non restare intrappolati negli ottimi locali del ceppo.
    Cap sulle famiglie meccaniche attive; sanity gate identico alle mutazioni."""
    active_fams = {family(s["id"]) for _, s in active_specs()}
    if len(active_fams) >= MAX_MECH_FAMILIES:
        print(f"\nseed: {len(active_fams)} famiglie attive ≥ cap {MAX_MECH_FAMILIES}, salto")
        return 0
    all_fams = sorted({family(s["id"]) for _, s in all_specs()})
    symbols = DEFAULT_SYMBOLS["perp"].split(",")
    datasets = {s: load_data(s, months) for s in symbols}

    prompt = f"""{REGISTRY_DOC}

{EXIT_DOC}
{lessons_block(None)}

Famiglie GIÀ esistenti (evita di duplicarne l'edge): {', '.join(all_fams)}

Proponi {N_SEEDS} strategie COMPLETAMENTE NUOVE in YAML (non mutazioni: edge diversi
dalle famiglie esistenti). Schema: id (kebab-case nuovo, suffisso -v1), thesis,
signals, entry (rule/direction), exit. Basket crypto: {','.join(symbols)}.
Obiettivo: edge ortogonali a momentum/breakout già coperti."""
    try:
        specs = [yaml.safe_load(c["yaml"]) for c in ask_glm(prompt)["candidates"]]
    except Exception as e:
        print(f"seed: generazione LLM fallita: {e}", file=sys.stderr)
        return 0

    promoted = 0
    for i, cand in enumerate(specs, 1):
        try:
            base = str(cand.get("id", f"seed-{i}")).rsplit("-v", 1)[0]
            if family(base) in all_fams:
                raise ValueError(f"famiglia già esistente: {base}")
            # validate() vuole un parent per risk/id: seed = parent di sé stesso
            # con risk conservativo di default
            pseudo_parent = {"id": f"{base}-v1", "risk": dict(DEFAULT_SEED_RISK)}
            spec = validate(cand, pseudo_parent, i)
            spec["parent"] = None                     # seed: nessun genitore reale
            res = eval_basket(spec, datasets)
            res.pop("basket_rets")
            spec["backtest"] = {f"basket_{months}m": res}
            agg = res["aggregate"]
            passes = agg["mean_sharpe"] > 0
            spec["status"] = "challenger" if passes else "candidate"
            if passes:
                spec.setdefault("paper_symbols", ",".join(symbols))
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            (OUT_DIR / f"{spec['id']}.yaml").write_text(
                yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
            flag = "✓ CHALLENGER" if passes else "· candidate (backtest ≤ 0)"
            print(f"  seed {spec['id']:<40} sharpe {agg['mean_sharpe']:+.2f} | {flag}")
            promoted += int(passes)
        except Exception as e:
            print(f"  seed {i} scartato: {e}", file=sys.stderr)
    return promoted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--seed", action="store_true",
                    help="forza il seed di famiglie nuove (di default: solo lunedì)")
    args = ap.parse_args()

    parents = pick_parents()
    pparents = pick_portfolio_parents()
    if not parents and not pparents:
        print("ERRORE: nessun ceppo attivo NÉ candidate riseminabili — evoluzione ferma",
              file=sys.stderr)
        sys.exit(1)

    total = 0
    for fam, (pf, ps) in parents.items():
        total += evolve_family(pf, ps, args.n, args.months)

    print(f"\n— evoluzione portfolio ({len(pparents)} famiglie) —")
    for fam, (pf, ps) in pparents.items():
        total += evolve_portfolio_family(pf, ps, args.n, args.months)

    if args.seed or datetime.now(timezone.utc).weekday() == 0:   # lunedì: sangue nuovo
        total += seed_new_families(args.months)

    print(f"\n{total} nuovi challenger in paper (gate: expectancy>0; il forward decide)")


if __name__ == "__main__":
    main()
