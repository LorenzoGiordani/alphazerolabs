"""Test della proiezione del funding storico sull'engine.

Verifica il behavior critico per l'onestà dei backtest: quando il tasso di
funding reale è NEGATIVO (short crowding in bear market), uno SHORT deve
PERDERE soldi sul funding (non incassare come farebbe con la costante legacy).
"""

import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import Backtest, _funding_rate_lookup, DEFAULT_FUNDING_HOURLY


def _candles(prices: list[float]) -> pd.DataFrame:
    ts = pd.date_range("2026-01-01", periods=len(prices), freq="1h", tz="UTC")
    o = np.r_[prices[0], prices[:-1]]
    return pd.DataFrame({"ts": ts, "open": o, "high": prices, "low": prices,
                         "close": prices, "volume": [100.0] * len(prices)})


def test_lookup_constant_when_no_history():
    c = _candles([100.0] * 5)
    got = _funding_rate_lookup(c, None, DEFAULT_FUNDING_HOURLY)
    assert got.shape == (5,)
    assert np.allclose(got, DEFAULT_FUNDING_HOURLY)


def test_lookup_projects_negative_rate_as_negative_hourly():
    # funding storico con rate negativo costante; step 8h -> orario = rate/8
    fh = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=3, freq="8h", tz="UTC"),
        "rate": [-0.0001, -0.0001, -0.0001],
    })
    c = _candles([100.0] * 10)
    got = _funding_rate_lookup(c, fh, DEFAULT_FUNDING_HOURLY)
    # ogni barra con funding noto deve essere -0.0001/8 < 0
    assert np.all(got[1:] < 0)
    assert np.allclose(got[1:], -0.0001 / 8.0)


def test_short_pays_when_funding_negative():
    """L'assert di onestà (relativo + segno): in regime di funding NEGATIVO uno
    short perde rispetto alla costante legacy positiva, e finisce sotto equity.
    Il numero di barre è alto (>100) così l'effetto funding cumulato domina la
    fee di ingresso one-shot e il test è robusto."""
    # prezzo piatto: nessun P&L direzionale, solo funding + fee di ingresso
    c = _candles([100.0] * 200)
    fh = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=40, freq="8h", tz="UTC"),
        "rate": [-0.0001] * 40,   # funding negativo -> short paga
    })

    def strat_short(_):
        return {"exposure": -1.0, "stop_pct": 50.0, "exit_cfg": {"max_leverage": 1.0}}

    # funding storico (onesto): equity DEVE scendere sotto il capitale iniziale
    eq_hist = Backtest(c, funding_hist=fh, max_leverage=1.0).run(strat_short)
    # funding legacy costante positivo: equity DEVE salire sopra il capitale iniziale
    eq_legacy = Backtest(c, max_leverage=1.0).run(strat_short)

    assert eq_hist["equity"].iloc[-1] < 10_000.0, "short deve perdere con funding negativo storico"
    assert eq_legacy["equity"].iloc[-1] > 10_000.0, "short deve incassare con costante positiva legacy"
    # la proprietà chiave: funding negativo batte funding positivo per uno short
    assert eq_hist["equity"].iloc[-1] < eq_legacy["equity"].iloc[-1]


def test_long_pays_when_funding_positive():
    c = _candles([100.0] * 50)
    fh = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=10, freq="8h", tz="UTC"),
        "rate": [0.0001] * 10,
    })

    def strat_long(_):
        return {"exposure": 1.0, "stop_pct": 50.0, "exit_cfg": {"max_leverage": 1.0}}

    eq = Backtest(c, funding_hist=fh, max_leverage=1.0).run(strat_long)
    assert eq["equity"].iloc[-1] < 10_000.0, "long deve pagare con funding positivo"
