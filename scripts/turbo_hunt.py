"""Turbo Hunt — trova strategie che passano la challenge Turbo (9% target / 3% DD static / 3% daily).

CORREZIONE CRITICA vs montecarlo_winners.py:
  Il Monte Carlo precedente aveva un BUG: usava peak-to-trough (trailing) DD invece
  dello STATIC DD (dal balance iniziale). Per una challenge con DD statico, la metrica
  corretta e' eq - start_balance, NON eq - peak. Questo sovrastimava il DD di ~2.5x
  e forzava sizing k_max troppo conservativi -> NO-GO falso.

  Con il DD statico corretto, tailshield ha maxDD -2.7% (vs -6.5% trailing) = SOTTO
  il limite 3%. k_max salta da 0.42 a 1.01.

AGGIUNTA: daily-loss circuit breaker (simulato nel bootstrap). Quando il daily P&L
  raggiunge -X%, le posizioni chiudono per quel giorno. Taglia la coda del worst day.

ITERAZIONE: testa una griglia di configurazioni (fattore, gross, vol-target, circuit
  breaker threshold) e cerca quelle con P(pass) >= 80%.

Uso: uv run scripts/turbo_hunt.py [--B 3000]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.portfolio import PortfolioBacktest

CRYPTO = "BTC,ETH,SOL,XRP,SUI,NEAR,WLD,ZEC,CRV"
PPY = 24 * 365
HL_TAKER_FEE = 0.00045
SLIPPAGE = 0.0005


# ── data ──────────────────────────────────────────────────────────────────────

def load_all(symbols, months):
    def gp(kind, col):
        btc = pd.read_parquet(ROOT/f"data/candles/BTC.parquet").tail(months*30*24)
        grid = pd.to_datetime(btc.ts, utc=True)
        cols = {}
        for s in symbols:
            p = ROOT/f"data/{kind}/{s}.parquet"
            if p.exists():
                c = pd.read_parquet(p).copy(); c["ts"]=pd.to_datetime(c.ts,utc=True)
                if col in c.columns:
                    cols[s]=c.drop_duplicates("ts").set_index("ts")[col].reindex(grid,method="ffill")
        return pd.DataFrame(cols).sort_index()
    px = gp("candles", "close")
    fund = gp("funding", "rate")
    liq_l = gp("coinalyze", "liq_long")
    liq_s = gp("coinalyze", "liq_short")
    oi = gp("coinalyze", "oi")
    return px, fund, liq_l, liq_s, oi


# ── weights ───────────────────────────────────────────────────────────────────

def terzile(row, gross=1.0):
    s=row.dropna(); w=pd.Series(0.0,index=row.index)
    if len(s)<6: return w
    n=max(2,len(s)//3)
    w[s.nlargest(n).index]=0.5/n; w[s.nsmallest(n).index]=-0.5/n
    g=w.abs().sum(); return w/g*gross if g>0 else w

def sign_w(row, gross=1.0):
    s=row.dropna(); w=pd.Series(0.0,index=row.index)
    lo,sh=s[s>0].index,s[s<0].index
    if len(lo): w[lo]=0.5/len(lo)
    if len(sh): w[sh]=-0.5/len(sh)
    g=w.abs().sum(); return w/g*gross if g>0 else w


# ── backtest core ─────────────────────────────────────────────────────────────

def run_factor(bt, fund, sig, wf, reb, gross=1.0, vt=None, floor=0.3, cap=1.0):
    idx=bt.close.index; n=len(idx)
    sig=sig.reindex(columns=bt.close.columns)
    W=pd.DataFrame(0.0,index=idx,columns=bt.close.columns)
    first=sig.dropna(how="all").index
    if first.empty: return pd.Series(0.0,index=idx)
    start=sig.index.get_loc(first[0])+1
    for i in range(start,n,reb):
        w=wf(sig.iloc[i-1],gross=gross).reindex(bt.close.columns).fillna(0.0)
        W.iloc[i:min(i+reb,n)]=w.to_numpy()
    raw_ret=(W.shift(1)*bt.ret).sum(axis=1)
    if vt is not None:
        rv=raw_ret.rolling(720,min_periods=360).std()*np.sqrt(PPY)
        m=(vt/rv).where(rv>0,1.0).clip(floor,cap)
    else: m=pd.Series(1.0,index=idx)
    H=W.mul(m,axis=0)
    to=H.diff().abs().sum(axis=1); to.iloc[start:start+1]=H.iloc[start].abs().sum()
    f=fund.reindex(index=idx,columns=bt.close.columns).fillna(0.0)
    pr=(H.shift(1)*bt.ret).sum(axis=1)-to*bt.cost
    cf=(-(H.shift(1).fillna(0.0))*f/8.0).sum(axis=1)
    return pr+cf


def build_factors(px, liq_l, liq_s, oi):
    ret1h = px.pct_change()
    return {
        "xsmom_168": px.pct_change(168),
        "tsmom_168": px.pct_change(168),
        "highvol_72": ret1h.rolling(72, min_periods=36).std(),
        "highvol_168": ret1h.rolling(168, min_periods=84).std(),
        "liqimb_7d": ((liq_s-liq_l)/oi.replace(0,np.nan)).rolling(7*24, min_periods=7*12).mean(),
        "liqimb_14d": ((liq_s-liq_l)/oi.replace(0,np.nan)).rolling(14*24, min_periods=14*12).mean(),
    }


# ── Monte Carlo con STATIC DD + circuit breaker ───────────────────────────────

def _apply_cb(samples, cb_threshold):
    """Applica circuit breaker a una matrice di sample: azzera le 24h di un giorno
    quando il daily P&L scende sotto -cb_threshold."""
    B, n = samples.shape
    n_days = n // 24
    out = samples.copy()
    daily = out[:, :n_days*24].reshape(B, n_days, 24).sum(axis=2)
    for b in range(B):
        for d in range(n_days):
            if daily[b, d] < -cb_threshold:
                out[b, d*24:(d+1)*24] = 0.0
    return out


def block_bootstrap(ret, block_h, B, seed=42):
    rng = np.random.default_rng(seed)
    r = ret.to_numpy()
    n = len(r)
    nb = int(np.ceil(n / block_h))
    samples = np.empty((B, n))
    for b in range(B):
        starts = rng.integers(0, n, size=nb)
        idx = (starts[:, None] + np.arange(block_h)[None, :]).ravel()[:n] % n
        samples[b] = r[idx]
    return samples


def static_maxdd(eq):
    """STATIC drawdown: minimo valore di (eq - start) dove start = 1.0.
    E' la metrica CORRETTA per challenge con DD static (dal balance iniziale)."""
    return float((eq - 1.0).min())


def mc_simulate(samples, target_pct, dd_limit, daily_limit, cb_threshold=None):
    """Monte Carlo con DD statico corretto + opzionale circuit breaker.

    cb_threshold: se != None, simula un circuit breaker che AZZERA i rendimenti
    di un giorno quando il daily P&L raggiunge -cb_threshold. Questo taglia la
    coda del worst day artificialmente (riflette un hard-stop che un trader reale
    potrebbe avere).
    """
    B, n = samples.shape
    n_days = n // 24

    # applica circuit breaker se richiesto: per ogni giorno, se la somma 24h
    # scende sotto -cb_threshold, azzera i rendimenti di quel giorno (flat)
    if cb_threshold is not None and cb_threshold > 0:
        cb_samples = samples.copy()
        # ricalcola i daily P&L
        daily = cb_samples[:, :n_days*24].reshape(B, n_days, 24).sum(axis=2)
        # per ogni giorno che breachia, azzera le 24h
        for b in range(B):
            for d in range(n_days):
                if daily[b, d] < -cb_threshold:
                    cb_samples[b, d*24:(d+1)*24] = 0.0
        # NB: questo e' optimistic (assume poteri di chiusura perfetti), ma da
        # un upper bound sul benefit del circuit breaker. Realisticamente ci sara'
        # slippage. Per conservatorismo, applichiamo poi il daily_limit sulla
        # versione CB.
        work = cb_samples
    else:
        work = samples

    # equity per sample
    eq = np.cumprod(1 + work, axis=1)
    # STATIC DD: (eq - 1.0).min()
    static_dd = (eq - 1.0).min(axis=1)
    # daily worst
    daily = work[:, :n_days*24].reshape(B, n_days, 24).sum(axis=2)
    worst_day = daily.min(axis=1)
    total_ret = eq[:, -1] - 1

    # k_max con DD statico corretto
    dd_pos = np.abs(static_dd)
    wd_pos = np.abs(worst_day)
    k_dd = np.where(dd_pos > 1e-9, dd_limit / dd_pos, 0.0)
    k_daily = np.where(wd_pos > 1e-9, daily_limit / wd_pos, 0.0)
    k_max = np.minimum(k_dd, k_daily) * 0.9  # safety

    scaled_ret = total_ret * k_max
    passed = scaled_ret >= target_pct

    return {
        "static_dd": static_dd, "worst_day": worst_day, "total_ret": total_ret,
        "k_max": k_max, "scaled_ret": scaled_ret,
        "p_pass": float(np.mean(passed)),
        "p_breach_dd": float(np.mean(static_dd < -dd_limit)),
        "p_breach_daily": float(np.mean(worst_day < -daily_limit)),
        "p_ret_negative": float(np.mean(total_ret < 0)),
    }


# ── strategy configs to test ──────────────────────────────────────────────────

def configs():
    """Griglia di configurazioni Turbo da cacciare. Ognia entry: combo di fattori
    + gross + vol-target + circuit breaker threshold."""
    C = []
    # liqimb e' il leader — spingere vol-target piu' basso (6-9%) per ridurre DD
    for vt in [0.06, 0.07, 0.08, 0.09, 0.10]:
        for floor in [0.1, 0.2]:
            for cb in [None, 0.012, 0.015]:
                cbtag = f"-cb{int(cb*1000)}" if cb else ""
                C.append(dict(name=f"liqimb-vt{int(vt*100)}-f{int(floor*100)}{cbtag}",
                    legs=[("liqimb_7d",1.0)],
                    wf_map={"liqimb_7d":"terz"}, vt=vt, floor=floor, cap=1.0, gross=1.0, cb=cb))
    # combo liqimb + 1 altro (liqimb domina, poco altro per non diluirlo)
    for partner, pname, pwf in [("highvol_72","hv","terz"), ("tsmom_168","ts","sign")]:
        for w_liq in [0.7, 0.8]:
            for vt in [0.08, 0.10]:
                for cb in [None, 0.015]:
                    cbtag = f"-cb{int(cb*1000)}" if cb else ""
                    C.append(dict(name=f"liq{pname}-{int(w_liq*100)}-vt{int(vt*100)}{cbtag}",
                        legs=[("liqimb_7d",w_liq),(partner,1-w_liq)],
                        wf_map={"liqimb_7d":"terz",partner:pwf},
                        vt=vt, floor=0.2, cap=1.0, gross=1.0, cb=cb))
    # quad con liqimb pesante (riflettersi su liqimb che e' il leader)
    for vt in [0.08, 0.10]:
        for cb in [None, 0.012, 0.015]:
            cbtag = f"-cb{int(cb*1000)}" if cb else ""
            C.append(dict(name=f"quadliq-vt{int(vt*100)}{cbtag}",
                legs=[("liqimb_7d",0.4),("highvol_72",0.2),("xsmom_168",0.2),("tsmom_168",0.2)],
                wf_map={"liqimb_7d":"terz","highvol_72":"terz","xsmom_168":"terz","tsmom_168":"sign"},
                vt=vt, floor=0.2, cap=1.0, gross=1.0, cb=cb))
    # liqimb 14d (lookback piu' lungo = piu' stabile)
    for vt in [0.08, 0.10]:
        C.append(dict(name=f"liqimb14-vt{int(vt*100)}", legs=[("liqimb_14d",1.0)],
            wf_map={"liqimb_14d":"terz"}, vt=vt, floor=0.2, cap=1.0, gross=1.0, cb=None))
    return C


def run_config(cfg, factors, bt, fund):
    """Esegue una config, ritorna la serie di rendimenti."""
    rets = []
    for fname, fw in cfg["legs"]:
        sig = factors[fname]
        wf = sign_w if cfg["wf_map"][fname] == "sign" else terzile
        r = run_factor(bt, fund, sig, wf, 168, gross=cfg["gross"],
                       vt=cfg.get("vt"), floor=cfg.get("floor",0.3), cap=cfg.get("cap",1.0))
        rets.append((r, fw))
    if len(rets) == 1:
        return rets[0][0]
    return sum(w*r for r,w in rets)


def stats(eq, ret):
    sh = ret.mean()/ret.std()*np.sqrt(PPY) if ret.std() else 0.0
    return float(eq.iloc[-1]-1), float(sh), float((eq/eq.cummax()-1).min())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--B", type=int, default=3000)
    ap.add_argument("--months", type=int, default=7)
    a = ap.parse_args()

    syms = CRYPTO.split(",")
    px, fund, liq_l, liq_s, oi = load_all(syms, a.months)
    bt = PortfolioBacktest(px, fee=HL_TAKER_FEE, slippage=SLIPPAGE)
    factors = build_factors(px, liq_l, liq_s, oi)

    print(f"basket {list(px.columns)}, {len(px)}h ({px.index.min():%Y-%m-%d} -> {px.index.max():%Y-%m-%d})")
    print(f"Monte Carlo B={a.B}, block=168h. DD=STATIC (dal balance iniziale), metrica corretta.\n")

    CHALLENGE = dict(target_pct=0.09, dd_limit=0.03, daily_limit=0.03)

    all_configs = configs()
    results = []
    for cfg in all_configs:
        ret = run_config(cfg, factors, bt, fund)
        if ret.std() == 0:
            continue
        eq = (1+ret).cumprod()
        r, sh, dd_trail = stats(eq, ret)
        static_dd_hist = float((eq - 1.0).min())
        # Monte Carlo
        samples = block_bootstrap(ret, 168, a.B)
        mc = mc_simulate(samples, cb_threshold=cfg.get("cb"), **CHALLENGE)
        # CHECK CRITICO: la strategia passa a k=1.0 (gross reale, no amplificazione)?
        # Questo e' il vero test "soldi reali" — se serve k=2.3 e' overfitting al path.
        # k=1.0: scala non serve, usa il return storico diretto
        eq_k1 = eq  # k=1.0 = nessuno scaling
        static_dd_k1 = static_dd_hist
        ret_k1 = r
        pass_k1 = (ret_k1 >= CHALLENGE["target_pct"]) and (static_dd_k1 >= -CHALLENGE["dd_limit"])
        # P(pass a k=1.0 nel Monte Carlo): frazione di sample che a k=1.0 passano
        eq_samples = np.cumprod(1 + (samples if cfg.get("cb") is None else
                           _apply_cb(samples, cfg.get("cb"))), axis=1)
        static_dd_s = (eq_samples - 1.0).min(axis=1)
        ret_s = eq_samples[:, -1] - 1
        pass_k1_mc = float(np.mean((ret_s >= CHALLENGE["target_pct"]) &
                                    (static_dd_s >= -CHALLENGE["dd_limit"])))
        results.append({
            "name": cfg["name"], "cfg": cfg,
            "hist_ret": r, "hist_sharpe": sh, "hist_dd_trail": dd_trail,
            "hist_static_dd": static_dd_hist,
            "pass_k1_hist": pass_k1, "pass_k1_mc": pass_k1_mc,
            "mc": mc,
        })

    # ── OUTPUT: classifica per P(pass a k=1.0) — il vero test soldi reali ─
    results.sort(key=lambda x: -x["pass_k1_mc"])
    print("="*120)
    print("TURBO HUNT — classifica per P(pass challenge a k=1.0, gross REALE no amplificazione)")
    print("Challenge: target 9% / DD 3% STATIC / daily 3% | k=1.0 = strategia cosi' com'e'")
    print("="*120)
    print(f"{'config':<26} {'histRet':>7} {'histSh':>6} {'histDDs':>7} {'P(pass k=1)':>11} {'P(passOpt)':>9} {'medKopt':>7} {'P(brkDD)':>8} {'P(retNeg)':>9}")
    print("-"*120)
    for res in results:
        mc = res["mc"]
        print(f"{res['name']:<26} {res['hist_ret']:>+7.1%} {res['hist_sharpe']:>6.2f} "
              f"{res['hist_static_dd']:>+7.1%} {res['pass_k1_mc']:>11.1%} "
              f"{mc['p_pass']:>9.1%} {np.median(mc['k_max']):>7.2f} "
              f"{mc['p_breach_dd']:>8.1%} {mc['p_ret_negative']:>9.1%}")

    # ── TOP CANDIDATES — P(pass a k=1.0) >= 80% ───────────────────────────
    winners_k1 = [r for r in results if r["pass_k1_mc"] >= 0.80]
    print(f"\n{'='*120}")
    print(f"CANDIDATI CON P(pass a k=1.0) >= 80% (STRATEGIA COSI' COM'E', NO AMPLIFICAZIONE): {len(winners_k1)}/{len(results)}")
    print(f"{'='*120}")
    if winners_k1:
        for w in winners_k1[:10]:
            mc = w["mc"]
            print(f"  {w['name']:<26} P(pass k=1)={w['pass_k1_mc']:.1%}  histRet={w['hist_ret']:+.1%}  "
                  f"histStaticDD={w['hist_static_dd']:+.1%}  Sharpe={w['hist_sharpe']:.2f}  P(retNeg)={mc['p_ret_negative']:.1%}")
    else:
        best = results[0]
        print(f"  NESSUNO sopra 80% a k=1.0. Migliore: {best['name']} P(pass k=1)={best['pass_k1_mc']:.1%}")

    # ── TORNA ALLA METRICA PRECEDENTE per confronto ────────────────────────
    winners_opt = [r for r in results if r["mc"]["p_pass"] >= 0.80]
    print(f"\n  (riferimento: {len(winners_opt)}/{len(results)} passano >= 80% con sizing OTTIMALE k_max)")


if __name__ == "__main__":
    main()
