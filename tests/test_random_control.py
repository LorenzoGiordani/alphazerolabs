"""Test del validatore random-control IC (Fase 0 piano integrazioni).

Prima di usare il permutation test per giudicare i segnali del registry,
il validatore stesso deve dimostrare di distinguere rumore da skill:
un segnale di puro rumore deve uscire `noise`, un segnale con skill
iniettata artificialmente deve uscire `confirmed_alive`, uno con skill
invertita `reversed`. Se questo test fallisce, ogni verdetto a valle
è inaffidabile.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.stats import (  # noqa: E402
    ic_random_control,
    rank_ic_series,
    shuffle_within_rows,
)

N_TS, N_SYM = 400, 10


def _panels(skill: float, seed: int = 7):
    """Panel sintetici: fwd = rumore; signal = skill*fwd + rumore."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=N_TS, freq="h")
    cols = [f"A{i}" for i in range(N_SYM)]
    fwd = pd.DataFrame(rng.standard_normal((N_TS, N_SYM)), idx, cols)
    noise = pd.DataFrame(rng.standard_normal((N_TS, N_SYM)), idx, cols)
    signal = skill * fwd + noise
    return signal, fwd


def test_pure_noise_is_noise():
    signal, fwd = _panels(skill=0.0)
    res = ic_random_control(signal, fwd, n_shuffles=30, seed=1)
    assert res["category"] == "noise", res


def test_injected_skill_confirmed():
    signal, fwd = _panels(skill=0.5)
    res = ic_random_control(signal, fwd, n_shuffles=30, seed=1)
    assert res["category"] == "confirmed_alive", res
    assert res["alpha_t"] > 3.5


def test_inverted_skill_reversed():
    signal, fwd = _panels(skill=-0.5)
    res = ic_random_control(signal, fwd, n_shuffles=30, seed=1)
    assert res["category"] == "reversed", res


def test_seed_deterministic():
    signal, fwd = _panels(skill=0.3)
    a = ic_random_control(signal, fwd, n_shuffles=20, seed=42)
    b = ic_random_control(signal, fwd, n_shuffles=20, seed=42)
    assert a == b


def test_shuffle_preserves_row_distribution_and_nan():
    rng = np.random.default_rng(0)
    df = pd.DataFrame(rng.standard_normal((50, 8)))
    df.iloc[0, 3] = np.nan
    df.iloc[10, :] = np.nan
    sh = shuffle_within_rows(df, seed=0)
    # NaN pinnati al loro posto
    assert np.isnan(sh.iloc[0, 3]) and sh.iloc[10].isna().all()
    # stessi valori per riga (permutazione, non alterazione)
    for i in (0, 1, 25, 49):
        a = np.sort(df.iloc[i].dropna().to_numpy())
        b = np.sort(sh.iloc[i].dropna().to_numpy())
        assert np.allclose(a, b)


def test_shuffle_destroys_information():
    """Lo shuffle di un segnale con skill deve avere IC ~0."""
    signal, fwd = _panels(skill=0.8)
    ic_real = rank_ic_series(signal, fwd).mean()
    ic_shuf = rank_ic_series(shuffle_within_rows(signal, seed=3), fwd).mean()
    assert ic_real > 0.3
    assert abs(ic_shuf) < 0.05


def test_short_sample_is_noise():
    signal, fwd = _panels(skill=0.9)
    res = ic_random_control(signal.head(10), fwd.head(10), n_shuffles=10)
    assert res["category"] == "noise" and res["n_obs"] < 30
