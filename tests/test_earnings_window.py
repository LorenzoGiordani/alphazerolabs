"""Regressione earnings_window: veto attivo solo nella finestra attesa,
causale (usa solo filed <= t), 0 sui simboli senza dati EDGAR."""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest.signals import earnings_window  # noqa: E402


def _candles(start="2026-01-01", hours=24 * 120):
    ts = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"ts": ts, "close": 100.0, "open": 100.0,
                         "high": 101.0, "low": 99.0, "volume": 1.0})


def test_no_earnings_data_is_zero():
    out = earnings_window({"candles": _candles(), "earnings": None})
    assert (out == 0).all()


def test_window_around_expected_filing():
    c = _candles()
    # ultimo filed noto: 2026-01-10 → atteso 2026-04-11 (+91g), veto [8/4, 12/4]
    earn = pd.DataFrame({"filed": [pd.Timestamp("2025-10-11"),
                                   pd.Timestamp("2026-01-10")]})
    out = earnings_window({"candles": c, "earnings": earn},
                          days_before=3, days_after=1)
    s = pd.Series(out.to_numpy(), index=c["ts"])
    assert s.loc["2026-04-09"].all() == 1      # dentro finestra
    assert s.loc["2026-04-12"].iloc[0] == 1    # bordo after
    assert s.loc["2026-03-01"].sum() == 0      # fuori
    assert s.loc["2026-04-20"].sum() == 0      # dopo
    # mai -1, solo gate
    assert set(s.unique()) <= {0, 1}


def test_causal_before_first_filed():
    c = _candles(start="2025-01-01", hours=24 * 30)
    earn = pd.DataFrame({"filed": [pd.Timestamp("2026-01-10")]})  # nel futuro
    out = earnings_window({"candles": c, "earnings": earn})
    assert (out == 0).all()  # nessun filed noto a t → nessuna finestra
