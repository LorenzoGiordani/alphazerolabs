"""Backtest a PORTAFOGLIO: pesi continui cross-asset, ribilanciamento periodico,
costo sul turnover. Per gli edge RELATIVI (cross-sectional momentum, risk parity,
market-neutral) che l'engine per-simbolo stop-based non cattura — l'edge sta nello
spread mantenuto, non nel singolo trade stoppato.

Anti-lookahead: i pesi a t usano solo dati ≤ t (ritorni trailing) e si applicano
dal bar successivo (shift). Niente stop intrabar qui: il rischio si controlla con
gross leverage, dollar-neutrality e ribilanciamento.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.engine import DEFAULT_SLIPPAGE, HL_TAKER_FEE


def xs_momentum_weights(trailing_ret: pd.Series, long_q: float = 0.66,
                        short_q: float = 0.33, gross: float = 1.0,
                        dollar_neutral: bool = True) -> pd.Series:
    """Pesi cross-sectional da un vettore di ritorni trailing (un timestamp).
    Long gli asset sopra il quantile long_q, short sotto short_q, equal-weight per
    gamba, scalati a `gross` (somma dei valori assoluti). dollar_neutral → Σpesi=0
    (market-neutral, netta il beta comune del basket)."""
    s = trailing_ret.dropna()
    w = pd.Series(0.0, index=trailing_ret.index)
    if len(s) < 3:
        return w
    hi, lo = s.quantile(long_q), s.quantile(short_q)
    longs, shorts = s[s >= hi].index, s[s <= lo].index
    if len(longs):
        w[longs] = 0.5 / len(longs)
    if len(shorts):
        w[shorts] = -0.5 / len(shorts)
    if not dollar_neutral:
        w = w.clip(lower=0.0)
    gabs = w.abs().sum()
    return w / gabs * gross if gabs > 0 else w


class PortfolioBacktest:
    """Simula un singolo portafoglio sull'intero basket. close = DataFrame
    (index ts, colonne simboli)."""

    def __init__(self, panel_close: pd.DataFrame, fee: float = HL_TAKER_FEE,
                 slippage: float = DEFAULT_SLIPPAGE):
        c = panel_close.sort_index()
        self.close = c[~c.index.duplicated()]
        self.ret = self.close.pct_change().fillna(0.0)
        self.cost = fee + slippage

    def run(self, weight_fn, lookback_h: int, rebalance_h: int):
        idx = self.close.index
        n = len(idx)
        trailing = self.close.pct_change(lookback_h)
        W = pd.DataFrame(0.0, index=idx, columns=self.close.columns)
        turnover = pd.Series(0.0, index=idx)
        last_w = pd.Series(0.0, index=self.close.columns)
        for i in range(lookback_h, n, rebalance_h):
            w = weight_fn(trailing.iloc[i]).reindex(self.close.columns).fillna(0.0)
            turnover.iloc[i] = (w - last_w).abs().sum()
            last_w = w
            W.iloc[i:min(i + rebalance_h, n)] = w.to_numpy()
        # pesi decisi a t, applicati dal bar successivo (no lookahead)
        port_ret = (W.shift(1) * self.ret).sum(axis=1) - turnover * self.cost
        equity = (1.0 + port_ret).cumprod()
        meta = {"rebalances": int((turnover > 0).sum()),
                "turnover_mean": float(turnover[turnover > 0].mean() or 0.0),
                "avg_gross": float(W.abs().sum(axis=1).replace(0, np.nan).mean())}
        return equity, port_ret, meta


def equal_weight_bh(panel_close: pd.DataFrame) -> pd.Series:
    """Benchmark: basket equal-weight buy&hold (long-only)."""
    ret = panel_close.sort_index().pct_change().fillna(0.0).mean(axis=1)
    return (1.0 + ret).cumprod()
