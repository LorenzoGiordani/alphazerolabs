"""Statistiche anti-overfitting: PSR, Deflated Sharpe, random-control IC.

Il loop evolutivo testa K candidati: il migliore ha uno Sharpe gonfiato per
selezione (è il massimo di K estrazioni, in parte rumore). Il DSR risponde a:
"probabilità che lo Sharpe osservato sia skill vero e non il massimo del
rumore su K prove?". Gate di promozione: DSR ≥ 0.95.

Il random-control IC risponde alla domanda complementare sui SEGNALI:
"l'IC osservato batte un segnale con la stessa distribuzione ma zero
informazione?". Un IC può passare il t-test vs zero ed essere comunque beta
condiviso del basket: lo shuffle cross-section per data preserva l'envelope
statistico e distrugge il mapping segnale→asset — null hypothesis onesta.
Soglia alpha_t 3.5 da Harvey-Liu-Zhu (2016) per multiple testing.

Riferimenti: Bailey & López de Prado, "The Deflated Sharpe Ratio" (2014);
Harvey, Liu & Zhu, "...and the Cross-Section of Expected Returns" (2016).
Design del random control ispirato a HKUDS/Vibe-Trading
bench_runner_strict.py (MIT). Niente scipy.
"""

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

_N = NormalDist()
_EULER = 0.5772156649015329


def sharpe_moments(rets: pd.Series) -> dict:
    """Momenti per-periodo dei ritorni (NON annualizzati: il PSR li vuole così)."""
    r = rets.dropna()
    n = len(r)
    if n < 30 or r.std(ddof=1) == 0:
        return {"sr": 0.0, "skew": 0.0, "kurt": 3.0, "n": n}
    return {"sr": float(r.mean() / r.std(ddof=1)),
            "skew": float(r.skew()),
            "kurt": float(r.kurt()) + 3.0,  # pandas dà l'eccesso → raw
            "n": n}


def psr(rets: pd.Series, sr0: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio: P(SR vero > sr0), con sr0 per-periodo.
    Corregge per campione corto, skew e code grasse."""
    m = sharpe_moments(rets)
    if m["n"] < 30:
        return 0.0
    denom = 1 - m["skew"] * m["sr"] + (m["kurt"] - 1) / 4 * m["sr"] ** 2
    if denom <= 0:
        return 0.0
    z = (m["sr"] - sr0) * math.sqrt(m["n"] - 1) / math.sqrt(denom)
    return float(_N.cdf(z))


def expected_max_sr(n_trials: int, var_trials: float) -> float:
    """Sharpe massimo atteso (per-periodo) di n_trials strategie SENZA skill."""
    if n_trials <= 1 or var_trials <= 0:
        return 0.0
    k = max(n_trials, 2)
    return math.sqrt(var_trials) * ((1 - _EULER) * _N.inv_cdf(1 - 1 / k)
                                    + _EULER * _N.inv_cdf(1 - 1 / (k * math.e)))


def rank_ic_series(x: pd.DataFrame, y: pd.DataFrame) -> pd.Series:
    """IC per timestamp = correlazione di rank cross-section tra x[t,:] e y[t,:].

    x, y: panel wide (index=ts, columns=symbol). Righe con <4 osservazioni
    valide producono NaN e vengono scartate."""
    xr = x.rank(axis=1)
    yr = y.rank(axis=1)
    xr = xr.sub(xr.mean(axis=1), axis=0)
    yr = yr.sub(yr.mean(axis=1), axis=0)
    num = (xr * yr).sum(axis=1)
    den = np.sqrt((xr**2).sum(axis=1) * (yr**2).sum(axis=1))
    valid = (x.notna() & y.notna()).sum(axis=1) >= 4
    return (num / den.replace(0, np.nan))[valid].dropna()


def shuffle_within_rows(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Permuta i valori finiti dentro ogni riga (cross-section per data).

    Preserva la distribuzione cross-section del segnale a ogni timestamp e
    distrugge il mapping segnale→asset: il risultato è un segnale a zero
    informazione con lo stesso envelope statistico dell'originale. NaN/inf
    restano al loro posto."""
    rng = np.random.default_rng(seed)
    out = df.to_numpy(dtype=float, copy=True)
    for i in range(out.shape[0]):
        idx = np.flatnonzero(np.isfinite(out[i]))
        if idx.size > 1:
            out[i, idx] = out[i, rng.permutation(idx)]
    return pd.DataFrame(out, index=df.index, columns=df.columns)


def ic_random_control(signal: pd.DataFrame, fwd: pd.DataFrame,
                      n_shuffles: int = 50, seed: int = 0,
                      alpha_t_threshold: float = 3.5,
                      min_ic_obs: int = 30) -> dict:
    """Permutation test dell'IC: il segnale batte la sua versione shuffled?

    signal: panel wide del segnale a t (già anti-lookahead: usa solo info ≤ t)
    fwd:    panel wide del forward return (già shiftato -hz dal chiamante)

    alpha_t = z-score permutazionale: (IC medio reale − media degli IC medi
    shuffled) / std degli IC medi shuffled. Categorie:
      confirmed_alive  alpha_t ≥ soglia (3.5, Harvey-Liu-Zhu)
      reversed         alpha_t ≤ −soglia (segnale reale ma invertito)
      noise            indistinguibile dal random (o campione < min_ic_obs)
    """
    ic = rank_ic_series(signal, fwd)
    n = len(ic)
    if n < min_ic_obs:
        return {"ic_mean": float(ic.mean()) if n else 0.0, "ic_t": 0.0,
                "n_obs": n, "random_ic_mean": 0.0, "random_ic_std": 0.0,
                "alpha_t": 0.0, "category": "noise"}
    ic_mean = float(ic.mean())
    ic_t = float(ic_mean / ic.std() * math.sqrt(n)) if ic.std() else 0.0
    rand_means = []
    for k in range(n_shuffles):
        ric = rank_ic_series(shuffle_within_rows(signal, seed=seed + k), fwd)
        if len(ric):
            rand_means.append(float(ric.mean()))
    rm = pd.Series(rand_means)
    rand_mean = float(rm.mean()) if len(rm) else 0.0
    rand_std = float(rm.std(ddof=1)) if len(rm) > 1 else 0.0
    alpha_t = (ic_mean - rand_mean) / rand_std if rand_std > 0 else 0.0
    if alpha_t >= alpha_t_threshold:
        category = "confirmed_alive"
    elif alpha_t <= -alpha_t_threshold:
        category = "reversed"
    else:
        category = "noise"
    return {"ic_mean": round(ic_mean, 4), "ic_t": round(ic_t, 2), "n_obs": n,
            "random_ic_mean": round(rand_mean, 4),
            "random_ic_std": round(rand_std, 4),
            "alpha_t": round(float(alpha_t), 2), "category": category}


def deflated_sharpe(rets: pd.Series, n_trials: int,
                    trial_srs: list[float] | None = None,
                    periods_per_year: int = 24 * 365) -> dict:
    """DSR = PSR contro lo Sharpe massimo atteso dal solo rumore su n_trials.

    rets: ritorni per-periodo della strategia candidata (es. orari, sul basket)
    trial_srs: Sharpe PER-PERIODO di tutti i candidati provati (stima la
               varianza cross-trial); se assente, usa la varianza dello
               stimatore dello SR del candidato stesso (conservativo)."""
    m = sharpe_moments(rets)
    if trial_srs and len(trial_srs) > 1:
        s = pd.Series(trial_srs)
        var_trials = float(s.var(ddof=1))
    else:
        var_trials = (1 - m["skew"] * m["sr"] + (m["kurt"] - 1) / 4 * m["sr"] ** 2) \
            / max(m["n"] - 1, 1)
    sr0 = expected_max_sr(n_trials, var_trials)
    ann = math.sqrt(periods_per_year)
    return {"dsr": psr(rets, sr0),
            "sr_ann": round(m["sr"] * ann, 3),
            "sr0_ann": round(sr0 * ann, 3),  # asticella: max atteso dal rumore
            "n_trials": n_trials}
