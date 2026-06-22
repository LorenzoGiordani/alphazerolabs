"""Test dell'engine a portafoglio (backtest/portfolio.py) e wiring spec."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.lifecycle import active_specs
from backtest.portfolio import PortfolioBacktest, equal_weight_bh, xs_momentum_weights
from backtest.strategy import load


def test_xs_weights_dollar_neutral():
    tr = pd.Series({"A": 0.30, "B": 0.20, "C": 0.00, "D": -0.10, "E": -0.30})
    w = xs_momentum_weights(tr, long_q=0.66, short_q=0.33, gross=1.0)
    assert abs(w.sum()) < 1e-9                      # dollar-neutral
    assert abs(w.abs().sum() - 1.0) < 1e-9          # gross = 1
    assert w["A"] > 0 and w["E"] < 0                # top long, bottom short


def test_xs_weights_too_few():
    w = xs_momentum_weights(pd.Series({"A": 0.1, "B": -0.1}))
    assert (w == 0).all()                           # <3 asset → nessun peso


def _panel(n=500, syms=("A", "B", "C", "D", "E")):
    ts = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    cols = {}
    for k, s in enumerate(syms):
        drift = 1 + (k - 2) * 0.0003                # drift diversi → rank cross-sectional stabile
        cols[s] = pd.Series(100.0 * np.cumprod(np.full(n, drift)), index=ts)
    return pd.DataFrame(cols)


def test_portfolio_backtest_runs():
    px = _panel()
    bt = PortfolioBacktest(px)
    eq, ret, meta = bt.run(xs_momentum_weights, lookback_h=168, rebalance_h=168)
    assert len(eq) == len(px)
    assert np.isfinite(eq.iloc[-1])
    assert meta["rebalances"] >= 1
    assert np.isfinite(equal_weight_bh(px).iloc[-1])


def test_portfolio_spec_excluded_from_mechanical_loop():
    spec = load(ROOT / "strategies/generated/xsmom-port-v1.yaml")
    assert spec["engine"] == "portfolio"
    assert "xsmom-port-v1" not in [s["id"] for _, s in active_specs()]
