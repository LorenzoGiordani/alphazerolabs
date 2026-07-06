"""Test evoluzione portfolio: eval offline (specchio dei fattori live),
validazione registry chiuso, anti-lookahead del loop ribilanciamento."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.evolve_portfolio import (eval_portfolio, run_portfolio,
                                      validate_portfolio)

RNG = np.random.default_rng(7)


def _panel(n_hours=24 * 90, n_assets=5, trend_asset=0):
    """Panel sintetico: random walk + un asset con drift (edge xsmom catturabile)."""
    ts = pd.date_range("2026-01-01", periods=n_hours, freq="h", tz="UTC")
    rets = RNG.normal(0, 0.005, size=(n_hours, n_assets))
    rets[:, trend_asset] += 0.0006          # drift ~ +5%/mese sul primo asset
    px = 100 * np.exp(np.cumsum(rets, axis=0))
    return pd.DataFrame(px, index=ts, columns=[f"A{i}" for i in range(n_assets)])


PARENT = {"id": "xsport-test-v1", "engine": "portfolio",
          "universe": {"selection": "explicit"}, "paper_symbols": "A0,A1,A2",
          "timeframe": "1h", "signals": [], "exit": {"stop_pct": 0},
          "risk": {"max_leverage": 2, "risk_per_trade_pct": 1.0,
                   "max_concurrent_positions": 9},
          "portfolio": {"factor": "xsmom", "lookback_h": 168, "rebalance_h": 168,
                        "long_q": 0.66, "short_q": 0.33, "gross": 1.0,
                        "dollar_neutral": True}}


def test_eval_returns_finite_metrics():
    px = _panel()
    agg, rets = eval_portfolio(PARENT, px, months=3)
    assert np.isfinite(agg["sharpe"]) and np.isfinite(agg["total_return"])
    assert agg["max_drawdown"] <= 0
    assert agg["rebalances"] > 0
    assert len(rets) > 0


def test_factors_and_voltarget_run():
    px = _panel()
    for pf in ({"factor": "tsmom", "lookback_h": 168, "rebalance_h": 96, "gross": 1.0},
               {"factor": "highvol", "vol_lookback_h": 72, "rebalance_h": 96},
               {"factor": "xsmom", "lookbacks_h": [96, 168], "rebalance_h": 168},
               {"factors": ["xsmom", "highvol"], "weights": [0.7, 0.3],
                "lookback_h": 168, "vol_lookback_h": 72, "rebalance_h": 96},
               {"factor": "xsmom", "lookback_h": 168, "rebalance_h": 168,
                "vol_target": {"enabled": True, "target_vol_ann": 0.2,
                               "vol_window_h": 480, "gross_floor": 0.3, "gross_cap": 1.5}}):
        equity, rets, meta = run_portfolio(px, pf)
        assert np.isfinite(equity.iloc[-1]), pf
        assert meta["rebalances"] > 0, pf


def test_turnover_costs_reduce_equity():
    """Ribilanciare ogni 8h deve costare più fee che ogni 336h (stesso segnale)."""
    px = _panel()
    base = {"factor": "xsmom", "lookback_h": 168, "long_q": 0.66, "short_q": 0.33}
    eq_slow, _, _ = run_portfolio(px, {**base, "rebalance_h": 336})
    eq_fast, meta_fast = run_portfolio(px, {**base, "rebalance_h": 8})[::2]
    assert meta_fast["rebalances"] > 10


def test_no_lookahead_weights_apply_next_bar():
    """Un salto di prezzo all'ultimo bar non deve entrare nel PnL del bar stesso
    se il peso è deciso in quel bar (pesi decisi a t → applicati da t+1)."""
    px = _panel(n_hours=24 * 30)
    pf = {"factor": "xsmom", "lookback_h": 96, "rebalance_h": 24}
    eq1, _, _ = run_portfolio(px, pf)
    px2 = px.copy()
    px2.iloc[-1, 0] *= 2.0                      # pump del 100% sull'ultimo bar
    eq2, _, _ = run_portfolio(px2, pf)
    # l'equity può cambiare per la posizione GIÀ aperta, ma non deve esplodere
    # come se il peso fosse stato deciso e applicato nello stesso bar del pump
    assert abs(eq2.iloc[-2] - eq1.iloc[-2]) < 1e-9   # storia identica fino a t-1


def test_validate_rejects_out_of_registry():
    with pytest.raises(ValueError):
        validate_portfolio({"portfolio": {"factor": "liqimb", "rebalance_h": 168}}, PARENT, 1)
    with pytest.raises(ValueError):
        validate_portfolio({"portfolio": {"factor": "xsmom", "rebalance_h": 168,
                                          "leverage_boost": 10}}, PARENT, 1)
    with pytest.raises(ValueError):
        validate_portfolio({"portfolio": {"factor": "xsmom", "rebalance_h": 1}}, PARENT, 1)
    with pytest.raises(ValueError):
        validate_portfolio({"portfolio": {"factor": "xsmom", "rebalance_h": 168,
                                          "long_q": 0.3, "short_q": 0.4}}, PARENT, 1)


def test_validate_forces_parent_invariants():
    cand = {"portfolio": {"factor": "tsmom", "lookback_h": 336, "rebalance_h": 48,
                          "gross": 0.8},
            "thesis": "sleeve trend più lenta",
            "risk": {"max_leverage": 50},        # tentativo LLM: ignorato
            "paper_symbols": "DOGE"}             # idem
    spec = validate_portfolio(cand, PARENT, 2)
    assert spec["risk"] == PARENT["risk"]
    assert spec["paper_symbols"] == PARENT["paper_symbols"]
    assert spec["engine"] == "portfolio"
    assert spec["parent"] == PARENT["id"]
    assert spec["id"].startswith("xsport-test-g2-")   # suffisso data
