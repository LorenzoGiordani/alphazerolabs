"""Studi empirici PRE-implementazione: verifica se l'edge esiste prima di costruirlo.

Ipotesi testate sul basket crypto (dati locali):
  A) Cross-sectional momentum  — ranka gli asset per ritorno passato → predice il
     ritorno relativo futuro? (IC + spread top-bottom)
  B) Funding carry             — funding alto (long affollati) → underperforma?
     (IC funding↔ritorno futuro, segno atteso NEGATIVO)
  C) Lead-lag BTC→alt          — il ritorno BTC a t-k predice le alt a t?
  D) Struttura di correlazione — quanto e direzionale-comune il basket (giustifica
     market-neutral / cap di correlazione)
  E) Distillazione desk        — cosa fa agents-v1 (l'unico vincitore): asset,
     direzione, RR proposto vs realizzato, win-rate.

Output: verdetto per ipotesi. Niente trading, solo misura. Uso:
  uv run scripts/research_edges.py [--symbols CSV] [--months 6]
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CRYPTO = "BTC,ETH,SOL,XRP,SUI,NEAR,WLD,ZEC,CRV"


def price_panel(symbols, months):
    cols = {}
    for s in symbols:
        p = ROOT / f"data/candles/{s}.parquet"
        if p.exists():
            c = pd.read_parquet(p).tail(months * 30 * 24)
            cols[s] = c.set_index("ts")["close"]
    panel = pd.DataFrame(cols).sort_index()
    panel = panel[~panel.index.duplicated()]
    return panel


def funding_panel(symbols, index):
    cols = {}
    for s in symbols:
        p = ROOT / f"data/funding/{s}.parquet"
        if p.exists():
            f = pd.read_parquet(p).set_index("ts")["rate"]
            f = f[~f.index.duplicated()].reindex(index, method="ffill")
            cols[s] = f
    return pd.DataFrame(cols)


def _row_ic(x: pd.DataFrame, y: pd.DataFrame) -> pd.Series:
    """IC per timestamp = correlazione cross-section (su rank) tra x[t,:] e y[t,:]."""
    xr = x.rank(axis=1)
    yr = y.rank(axis=1)
    xr = xr.sub(xr.mean(axis=1), axis=0)
    yr = yr.sub(yr.mean(axis=1), axis=0)
    num = (xr * yr).sum(axis=1)
    den = np.sqrt((xr**2).sum(axis=1) * (yr**2).sum(axis=1))
    return (num / den.replace(0, np.nan)).dropna()


def _spread(signal: pd.DataFrame, fwd: pd.DataFrame, sample: int) -> float:
    """Ritorno medio: long meta alta del signal − short meta bassa, campionato ogni `sample`h."""
    out = []
    rows = signal.dropna(how="all").index[::sample]
    for t in rows:
        s, f = signal.loc[t], fwd.loc[t]
        ok = s.notna() & f.notna()
        if ok.sum() < 4:
            continue
        s, f = s[ok], f[ok]
        med = s.median()
        hi = f[s >= med].mean()
        lo = f[s < med].mean()
        out.append(hi - lo)
    return float(np.nanmean(out)) if out else float("nan")


def study_cross_sectional(panel, lb=168, hz=168):
    past = panel.pct_change(lb)
    fwd = panel.pct_change(hz).shift(-hz)
    ic = _row_ic(past, fwd)
    spread = _spread(past, fwd, hz)
    tstat = ic.mean() / ic.std() * np.sqrt(len(ic)) if ic.std() else 0
    print(f"\n[A] CROSS-SECTIONAL MOMENTUM  (lb {lb}h, fwd {hz}h)")
    print(f"  IC medio {ic.mean():+.3f}  (t {tstat:+.1f}, n {len(ic)})")
    print(f"  spread top−bottom {spread:+.2%} sul fwd window")
    verdict = "SEGNALE" if abs(tstat) > 2 and ic.mean() > 0 else "debole/assente"
    print(f"  → momentum relativo: {verdict}")


def study_funding_carry(panel, fund, hz=168):
    fwd = panel.pct_change(hz).shift(-hz)
    common = [c for c in fund.columns if c in fwd.columns]
    fund, fwd2 = fund[common], fwd[common]
    ic = _row_ic(fund, fwd2)
    spread = _spread(fund, fwd2, hz)   # long high funding − short low (per misurare il segno)
    tstat = ic.mean() / ic.std() * np.sqrt(len(ic)) if ic.std() else 0
    print(f"\n[B] FUNDING CARRY  (fwd {hz}h, {len(common)} asset)")
    print(f"  IC funding↔fwdRet {ic.mean():+.3f}  (t {tstat:+.1f}, n {len(ic)})  [atteso NEGATIVO]")
    print(f"  spread highFund−lowFund {spread:+.2%}  → se <0, short-high-funding paga")
    verdict = "SEGNALE (short high funding)" if tstat < -2 else ("SEGNALE (long high funding)" if tstat > 2 else "debole/assente")
    print(f"  → carry: {verdict}")


def study_lead_lag(panel, leader="BTC", lags=(0, 1, 2, 3, 6, 12, 24)):
    ret = panel.pct_change()
    if leader not in ret:
        print("\n[C] LEAD-LAG: leader assente"); return
    alts = [c for c in ret.columns if c != leader]
    print(f"\n[C] LEAD-LAG  {leader}→alt (corr media su {len(alts)} alt)")
    base = None
    for k in lags:
        cs = [ret[leader].shift(k).corr(ret[a]) for a in alts]
        m = float(np.nanmean(cs))
        if k == 0:
            base = m
        tag = " (contemporaneo)" if k == 0 else (f"  Δvs k0 {m-base:+.3f}" if base else "")
        print(f"  k={k:>2}h  corr {m:+.3f}{tag}")
    print("  → se corr a k>0 resta alta vs k0, BTC anticipa (catch-up tradabile)")


def study_correlation(panel):
    ret = panel.pct_change()
    cm = ret.corr()
    iu = cm.where(~np.eye(len(cm), dtype=bool))
    mean_pair = float(iu.stack().mean())
    print(f"\n[D] CORRELAZIONE basket ({len(cm)} asset)")
    print(f"  corr media a coppie {mean_pair:+.2f}")
    print("  → alta = un long-basket e quasi 1 scommessa; market-neutral/cap correlazione sensati"
          if mean_pair > 0.4 else "  → bassa: diversificazione gia presente")


def study_desk():
    dec = [json.loads(l) for l in (ROOT / "paper/decisions.jsonl").read_text().splitlines() if l.strip()]
    fin = [d for d in dec if d.get("stage") == "final" and d.get("proposal", {}).get("action") == "trade"]
    print(f"\n[E] DISTILLAZIONE DESK agents-v1  ({len(fin)} proposte di trade)")
    if fin:
        sym = Counter(d["proposal"]["symbol"] for d in fin)
        dirn = Counter(d["proposal"]["direction"] for d in fin)
        trs = [float(d["proposal"].get("target_r", 0)) for d in fin if d["proposal"].get("target_r")]
        stops = [float(d["proposal"].get("stop_pct", 0)) for d in fin if d["proposal"].get("stop_pct")]
        print(f"  asset più scelti: {dict(sym.most_common(6))}")
        print(f"  direzione: {dict(dirn)}")
        print(f"  target_r proposto: media {np.mean(trs):.2f}, mediana {np.median(trs):.2f}")
        print(f"  stop_pct proposto: media {np.mean(stops):.2f}%")
    j = [json.loads(l) for l in (ROOT / "paper/journal.jsonl").read_text().splitlines() if l.strip()]
    opens, closed = {}, []
    for e in j:
        if e.get("strategy") != "agents-v1":
            continue
        if e.get("type") == "open":
            opens[e["symbol"]] = e
        elif e.get("type") == "close":
            o = opens.pop(e["symbol"], None)
            if o:
                risk = abs(o["stop_px"] / o["entry_px"] - 1) * o["size_usd"]
                closed.append({"sym": e["symbol"], "pnl": e.get("pnl_usd", 0.0),
                               "r": e.get("pnl_usd", 0.0) / risk if risk > 0 else 0.0,
                               "reason": e.get("reason")})
    if closed:
        n = len(closed)
        wins = sum(1 for c in closed if c["pnl"] > 0)
        print(f"  REALIZZATO: {n} chiusure, win-rate {wins/n:.0%}, "
              f"PnL {sum(c['pnl'] for c in closed):+.0f}$, R medio {np.mean([c['r'] for c in closed]):+.2f}")
        print(f"  uscite: {dict(Counter(c['reason'] for c in closed))}")
        print(f"  R medio vincenti {np.mean([c['r'] for c in closed if c['pnl']>0] or [0]):+.2f} vs "
              f"perdenti {np.mean([c['r'] for c in closed if c['pnl']<=0] or [0]):+.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=CRYPTO)
    ap.add_argument("--months", type=int, default=6)
    a = ap.parse_args()
    syms = a.symbols.split(",")
    panel = price_panel(syms, a.months)
    fund = funding_panel(syms, panel.index)
    print(f"basket {list(panel.columns)}, {len(panel)} ore "
          f"({panel.index.min():%Y-%m-%d} → {panel.index.max():%Y-%m-%d})")
    study_cross_sectional(panel)
    study_funding_carry(panel, fund)
    study_lead_lag(panel)
    study_correlation(panel)
    study_desk()


if __name__ == "__main__":
    main()
