"""F2 step finale: backtest portfolio dei survivor dello zoo sweep.

Gate pre-registrato (Obsidian, piano integrazioni): dallo sweep
(paper/zoo_sweep.json) si selezionano MAX 3 candidati mutuamente diversi
(|overlap| < 0.7 fra loro, temi distinti), backtest dollar-neutral
walk-forward con fee+slippage di validazione, e passano SOLO se:
  Sharpe basket >= 1.0  E  DSR >= 0.95 con n_trials=456  E  OOS 8m/4m regge
(alpha_t < 0 allo sweep => segnale INVERTITO, dichiarato nell'output).

Zero sopravvissuti = risultato valido ("fattori equity non trasferiscono").
Uso: uv run scripts/research_zoo_backtest.py [--months 12] [--top 3]
"""
import argparse
import importlib
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.stats import deflated_sharpe, rank_ic_series  # noqa: E402
from scripts.research_zoo import daily_panel  # noqa: E402
from scripts.robustness_portfolio import (  # noqa: E402
    _bt, run_book, terzile_weights,
)

CRYPTO = "BTC,ETH,SOL,XRP,SUI,NEAR,WLD,ZEC,CRV"
PPY = 24 * 365
N_TRIALS = 456          # pre-registrato: l'intero zoo testato
REBALANCE_H = 168
MIN_SHARPE = 1.0
MIN_DSR = 0.95
MAX_MUTUAL_OVERLAP = 0.7


def hourly_close(symbols, months):
    cols = {}
    for s in symbols:
        p = ROOT / f"data/candles/{s}.parquet"
        if p.exists():
            c = pd.read_parquet(p).tail(months * 30 * 24)
            cols[s] = c.set_index("ts")["close"]
    px = pd.DataFrame(cols).sort_index()
    return px[~px.index.duplicated()]


def factor_signal(fid: str, panel: dict) -> pd.DataFrame | None:
    zoo = fid.split("_")[0]
    stem = fid[len(zoo) + 1:]
    for cand in (f"vendor.vibe_zoo.zoo.{zoo}.alpha_{stem}",
                 f"vendor.vibe_zoo.zoo.{zoo}.{stem}",
                 f"vendor.vibe_zoo.zoo.{zoo}.{fid}"):
        try:
            return importlib.import_module(cand).compute(panel)
        except ModuleNotFoundError:
            continue
    return None


def pick_diverse(survivors: list[dict], panel: dict, top: int) -> list[dict]:
    """Greedy: scorri per |alpha_t_7d| decrescente, tieni chi ha overlap
    mutuo < soglia con i gia scelti."""
    chosen, sigs = [], []
    for s in sorted(survivors, key=lambda r: -abs(r["alpha_t_7d"])):
        sig = factor_signal(s["id"], panel)
        if sig is None:
            continue
        sig = sig.replace([np.inf, -np.inf], np.nan)
        if any(abs(rank_ic_series(sig, prev).mean()) >= MAX_MUTUAL_OVERLAP
               for prev in sigs):
            continue
        chosen.append(s)
        sigs.append(sig)
        if len(chosen) == top:
            break
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=CRYPTO)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--top", type=int, default=3)
    a = ap.parse_args()
    warnings.filterwarnings("ignore")

    sweep = json.loads((ROOT / "paper/zoo_sweep.json").read_text())
    survivors = sweep["survivors"]
    syms = a.symbols.split(",")
    dpanel = daily_panel(syms, a.months)
    px = hourly_close(syms, a.months)
    bt = _bt(px)
    train_end = px.index[0] + pd.Timedelta(days=8 * 30)

    picked = pick_diverse(survivors, dpanel, a.top)
    print(f"candidati selezionati (diversita mutua < {MAX_MUTUAL_OVERLAP}): "
          f"{[p['id'] for p in picked]}")

    results = []
    for s in picked:
        sig_d = factor_signal(s["id"], dpanel).replace([np.inf, -np.inf], np.nan)
        inverted = s["alpha_t_7d"] < 0
        if inverted:
            sig_d = -sig_d
        # daily -> griglia oraria (ffill: il valore di ieri vale fino al prossimo)
        sig_h = sig_d.shift(1).reindex(px.index, method="ffill")
        eq, ret, n_reb = run_book(sig_h, bt, terzile_weights, REBALANCE_H)
        sharpe = float(ret.mean() / ret.std() * np.sqrt(PPY)) if ret.std() else 0.0
        maxdd = float((eq / eq.cummax() - 1).min())
        dsr = deflated_sharpe(ret, N_TRIALS, periods_per_year=PPY)["dsr"]
        r_tr, r_te = ret[ret.index <= train_end], ret[ret.index > train_end]
        sh_tr = float(r_tr.mean() / r_tr.std() * np.sqrt(PPY)) if r_tr.std() else 0.0
        sh_te = float(r_te.mean() / r_te.std() * np.sqrt(PPY)) if r_te.std() else 0.0
        passed = sharpe >= MIN_SHARPE and dsr >= MIN_DSR and sh_te > 0
        results.append({"id": s["id"], "zoo": s["zoo"], "theme": s.get("theme"),
                        "inverted": inverted, "ret": round(float(eq.iloc[-1] - 1), 4),
                        "sharpe": round(sharpe, 2), "maxdd": round(maxdd, 3),
                        "dsr": round(float(dsr), 3), "sharpe_train_8m": round(sh_tr, 2),
                        "sharpe_test_4m": round(sh_te, 2), "n_rebalances": n_reb,
                        "passed": bool(passed)})
        flag = "PASS" if passed else "FAIL"
        print(f"  {s['id']:16s} inv={inverted}  ret {eq.iloc[-1]-1:+7.1%}  "
              f"Sharpe {sharpe:+.2f}  maxDD {maxdd:.1%}  DSR {dsr:.3f}  "
              f"OOS(4m) {sh_te:+.2f}  -> {flag}")

    out = {"asof": datetime.now(timezone.utc).isoformat(),
           "protocol": {"min_sharpe": MIN_SHARPE, "min_dsr": MIN_DSR,
                        "n_trials": N_TRIALS, "rebalance_h": REBALANCE_H,
                        "oos_split": "8m/4m", "fees": "taker 4.5bps + slip 5bps"},
           "results": results,
           "verdict": ("PROMUOVI A CHALLENGER PAPER i passed"
                       if any(r["passed"] for r in results)
                       else "ZOO FALSIFICATO sul basket crypto: nessun candidato "
                            "passa il gate (risultato valido, lezione pubblica)")}
    (ROOT / "paper/zoo_backtest.json").write_text(json.dumps(out, indent=1))
    print(f"\nverdetto: {out['verdict']}")
    print("→ paper/zoo_backtest.json")


if __name__ == "__main__":
    main()
