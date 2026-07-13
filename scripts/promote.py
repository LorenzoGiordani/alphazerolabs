"""Promozione/retrocessione automatica delle strategie sulla performance PAPER.

Per ogni famiglia (ceppo evolutivo):
  - challenger che batte il champion con campione sufficiente → champion
  - vecchio champion battuto → retired (resta visibile: è la storia)
  - challenger in perdita con campione sufficiente → retired

Gate conservativi (anti-rumore): per le strategie per-trade servono MIN_CLOSED
trade chiusi e un contratto di evidenza verificato (DSR, OOS, checker
indipendente). I portfolio non sono auto-promovibili: i loro heartbeat sono
autocorrelati e non equivalgono a osservazioni indipendenti.

Uso: .venv/bin/python scripts/promote.py [--min-trades 20] [--dry-run]
"""

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.evidence import verify_evidence
from backtest.lifecycle import (ROOT, all_specs, family,
                                paper_stats, set_status)
from scripts.review import append_lesson

LIFECYCLE_LOG = ROOT / "paper" / "lifecycle.jsonl"
LESSONS = ROOT / "paper" / "lessons.jsonl"

MIN_SHARPE = 0.3   # sharpe_r minimo per essere "champion material"
MARGIN = 0.2       # il challenger deve battere il champion di questo margine (sharpe_r)
MAX_DD_PCT = 15.0  # drawdown equity oltre il quale ritira anche con pochi trade chiusi
ZOMBIE_DAYS = 14   # challenger evolutivo con 0 trade chiusi dopo N giorni → retired
                   # (libera slot nel cap famiglia di evolve_auto; precedente:
                   # glm-regime-confluence ritirata come zombie, gate sempre chiuso)


def _age_days(spec: dict) -> int | None:
    """Giorni dalla creazione (campo `created` dello YAML), None se assente."""
    created = spec.get("created")
    if not created:
        return None
    try:
        return (datetime.now(timezone.utc).date() - date.fromisoformat(str(created))).days
    except ValueError:
        return None


def log_event(rec: dict) -> None:
    rec["logged_at"] = datetime.now(timezone.utc).isoformat()
    LIFECYCLE_LOG.parent.mkdir(exist_ok=True)
    with LIFECYCLE_LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def add_lesson(strategy: str, verdict: str, lesson: str, tags: list[str]) -> None:
    """Canale unificato via review.append_lesson (regola 7). Schema compatibile
    con --add: trade_key, symbol=basket, verdict, lesson, tags."""
    rec = {"trade_key": f"lifecycle|{strategy}|{datetime.now(timezone.utc):%Y-%m-%d}",
           "symbol": "basket", "strategy": strategy, "verdict": verdict,
           "lesson": lesson, "tags": tags}
    append_lesson(rec)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-trades", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    specs = {s["id"]: (f, s) for f, s in all_specs()
             if s.get("status") in ("champion", "challenger")}
    fams: dict[str, list] = {}
    for sid, (f, s) in specs.items():
        fams.setdefault(family(sid), []).append((f, s, paper_stats(sid)))

    changes = 0
    for fam, members in sorted(fams.items()):
        champ = next((m for m in members if m[1]["status"] == "champion"), None)
        challengers = [m for m in members if m[1]["status"] == "challenger"]
        champ_sharpe = champ[2].get("basket_sharpe_r", champ[2]["sharpe_r"]) if champ else None
        print(f"\n[{fam}] champion={champ[1]['id'] if champ else '—'} "
              f"(basket_sharpe {champ_sharpe if champ else 'n/a'}), challenger={len(challengers)}")

        # 1. ritira i challenger chiaramente perdenti (campione sufficiente o DD grave)
        # Usa basket_mean_r (mean R per-asset, regola 5): pooled maschererebbe
        # strategie che vincono su 1 asset e perdono sugli altri.
        #
        # ECCEZIONE engine:portfolio: n_closed qui e' il # di letture rebalance/heartbeat
        # (cron ogni 4h, autocorrelate), NON trade indipendenti. basket_mean_r e' il
        # ritorno per-rebalance su pochi giorni = rumore (lezione: xsmom-port ritirata
        # dopo 4 giorni su mean_r -0.00049, falsa ritirazione). L'edge di un portfolio
        # e' uno Sharpe lento su MESI; non si falsifica da poche letture. Per i
        # portfolio vale SOLO il breach di drawdown (hard risk limit); oltre quello
        # serve tempo (cfr. README: il gate M5 e' TEMPO non codice).
        retired_ids: set[str] = set()
        for f, s, st in challengers:
            is_portfolio = s.get("engine") == "portfolio"
            dd = st.get("equity_dd_pct", 0.0)
            bmr = st.get("basket_mean_r", st.get("mean_r", 0.0))
            print(f"  challenger {s['id']}: {st['n_closed']} chiusi, "
                  f"basket_sharpe {st.get('basket_sharpe_r', 0.0)}, "
                  f"basket_meanR {bmr}, PnL {st['total_pnl']}$, DD {dd}%, "
                  f"symbols {st.get('symbols_traded', 0)}"
                  + ("  [portfolio: gate mean_r sospeso]" if is_portfolio else ""))
            if dd <= -MAX_DD_PCT:
                print(f"    → RETIRE (drawdown {dd}% >= {MAX_DD_PCT}% con {st['n_closed']} trade)")
                if not args.dry_run:
                    set_status(f, "retired")
                    log_event({"event": "retire", "strategy": s["id"], "family": fam, "stats": st,
                               "reason": "drawdown_breach"})
                    add_lesson(s["id"], "thesis_wrong",
                               f"Ritirata da challenger: drawdown equity {dd}% "
                               f"(soglia -{MAX_DD_PCT}%), {st['n_closed']} trade chiusi. "
                               f"Perdita grave precoce — l'edge è falsificato dal capitale a rischio.",
                               (["lifecycle", "retire", "paper", "drawdown"]
                                + (["portfolio"] if is_portfolio else [])))
                changes += 1
                retired_ids.add(s["id"])
            elif (s.get("parent") and st["n_closed"] == 0
                  and _age_days(s) is not None and _age_days(s) >= ZOMBIE_DAYS):
                # zombie: mutazione evolutiva che non ha MAI tradato — gate d'ingresso
                # mai aperto. Occupa uno slot del cap famiglia senza produrre dati.
                # Solo figli evolutivi (campo parent): i reseed manuali restano.
                print(f"    → RETIRE (zombie: 0 trade in {_age_days(s)} giorni)")
                if not args.dry_run:
                    set_status(f, "retired")
                    log_event({"event": "retire", "strategy": s["id"], "family": fam, "stats": st,
                               "reason": "zombie_no_trades"})
                    add_lesson(s["id"], "thesis_wrong",
                               f"Ritirata da challenger: 0 trade chiusi in {_age_days(s)} giorni "
                               f"(soglia {ZOMBIE_DAYS}). Entry rule mai soddisfatta — mutazione "
                               f"sterile, nessun dato raccolto.",
                               ["lifecycle", "retire", "paper", "zombie"])
                changes += 1
                retired_ids.add(s["id"])
            elif not is_portfolio and st["n_closed"] >= args.min_trades and bmr < 0:
                # per-simbolo: n_closed sono trade discreti, mean_r negativo = edge falsificato
                print(f"    → RETIRE (perdente con {st['n_closed']} trade, basket_meanR<0)")
                if not args.dry_run:
                    set_status(f, "retired")
                    log_event({"event": "retire", "strategy": s["id"], "family": fam, "stats": st,
                               "reason": "basket_mean_r_negative"})
                    add_lesson(s["id"], "thesis_wrong",
                               f"Ritirata da challenger: {st['n_closed']} trade paper, "
                               f"basket_meanR {bmr} (perdente su media per-asset). "
                               f"Il paper trading ha falsificato l'edge.",
                               ["lifecycle", "retire", "paper"])
                changes += 1
                retired_ids.add(s["id"])

        # 2. miglior challenger qualificato (basket_sharpe_r + DSR gate, regole 5 + 10)
        # DSR: gate anti-overfitting. Il challenger deve avere DSR >= MIN_DSR dal
        # backtest (salvato in spec.backtest.aggregate.dsr da evolve.py). Promuovere
        # senza DSR = promuovere rumore selezionato (lezione FINSABER/Profit Mirage).
        for _, strategy, _ in challengers:
            if strategy.get("engine") == "portfolio" and strategy["id"] not in retired_ids:
                print(f"  {strategy['id']}: portfolio — auto-promozione bloccata; "
                      "richiede gate temporale/rebalance indipendente")
        qual = [(f, s, st) for f, s, st in challengers if s["id"] not in retired_ids
                if s.get("engine") != "portfolio"
                if st["n_closed"] >= args.min_trades and st.get("basket_mean_r", 0) > 0
                and st.get("basket_sharpe_r", 0) >= MIN_SHARPE]
        if not qual:
            continue
        best = max(qual, key=lambda m: m[2].get("basket_sharpe_r", 0.0))
        bf, bs, bst = best

        evidence = verify_evidence(bs, ROOT)
        if not evidence["verified"]:
            print(f"  {bs['id']}: evidenza non verificata — promozione bloccata "
                  f"({', '.join(evidence['reasons'])})")
            continue
        dsr = evidence["dsr"]

        beats = champ_sharpe is None or bst.get("basket_sharpe_r", 0.0) >= champ_sharpe + MARGIN
        if not beats:
            print(f"  {bs['id']} (basket_sharpe {bst.get('basket_sharpe_r', 0.0)}) "
                  f"non batte il champion di {MARGIN}")
            continue

        print(f"  → PROMOTE {bs['id']} a champion (basket_sharpe {bst.get('basket_sharpe_r', 0.0)}, "
              f"DSR {dsr if dsr is not None else 'n/a'})")
        if not args.dry_run:
            if champ:
                set_status(champ[0], "retired")
                log_event({"event": "dethrone", "strategy": champ[1]["id"], "family": fam,
                           "by": bs["id"], "stats": champ[2]})
            set_status(bf, "champion")
            log_event({"event": "promote", "strategy": bs["id"], "family": fam, "stats": bst,
                       "dsr": dsr, "evidence_status": "verified",
                       "maker_run_id": evidence["maker_run_id"],
                       "checker_run_id": evidence["checker_run_id"]})
            add_lesson(bs["id"], "thesis_right",
                       f"Promossa a CHAMPION: {bst['n_closed']} trade paper, basket_sharpe "
                       f"{bst.get('basket_sharpe_r', 0.0)}, DSR {dsr}, win {bst['win_rate']}, "
                       f"PnL {bst['total_pnl']}$. "
                       + (f"Spodesta {champ[1]['id']}." if champ else "Primo champion della famiglia."),
                       ["lifecycle", "promote", "paper", "champion"])
        changes += 1

    print(f"\n{changes} cambi di stato" + (" (dry-run, nessuna modifica)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
