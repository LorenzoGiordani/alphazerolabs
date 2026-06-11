"""Registry segnali leading/strutturali — gli unici componibili dalle strategie.

Niente indicatori mainstream/lagging (no SMA/RSI/MACD — decisione 11/06).
Ogni segnale: f(data, **params) -> pd.Series di {-1, 0, +1} allineata a
data["candles"] (indice 0..n-1). Il segno è la *lettura* del segnale
(es. +1 = crowding long), la direzione del trade la decide la strategia.

data: {"candles": df, "funding": df|None (ts, rate 8h), "flow": df|None (ts, volume, taker_buy)}
"""

import numpy as np
import pandas as pd


def _align(candles: pd.DataFrame, other: pd.DataFrame, col: str) -> pd.Series:
    """Allinea serie esterna alle candele via merge_asof (solo dati ≤ t)."""
    merged = pd.merge_asof(candles[["ts"]], other.sort_values("ts"), on="ts", direction="backward")
    return merged[col]


def funding_percentile(data, lookback_h: int = 168, extreme_pct: float = 90) -> pd.Series:
    """+1 = funding a estremo positivo (crowding long), -1 = estremo negativo."""
    candles = data["candles"]
    if data.get("funding") is None:
        return pd.Series(0, index=candles.index)
    rate = _align(candles, data["funding"], "rate").fillna(0.0)
    pct = rate.abs().rolling(lookback_h, min_periods=lookback_h // 2).rank(pct=True) * 100
    out = np.where((pct >= extreme_pct) & (rate > 0), 1, np.where((pct >= extreme_pct) & (rate < 0), -1, 0))
    return pd.Series(out, index=candles.index)


def range_breakout(data, range_h: int = 48, volume_confirm_mult: float = 2.0) -> pd.Series:
    """+1 = chiusura sopra il massimo del range precedente con volume, -1 = sotto il minimo."""
    c = data["candles"]
    hi = c.high.rolling(range_h).max().shift(1)
    lo = c.low.rolling(range_h).min().shift(1)
    vol_ok = c.volume > volume_confirm_mult * c.volume.rolling(range_h).mean().shift(1)
    out = np.where((c.close > hi) & vol_ok, 1, np.where((c.close < lo) & vol_ok, -1, 0))
    return pd.Series(out, index=c.index)


def taker_flow(data, lookback_h: int = 24, threshold: float = 0.06) -> pd.Series:
    """+1 = aggressori in acquisto (taker buy ratio > 0.5+thr), -1 = in vendita."""
    candles = data["candles"]
    flow = data.get("flow")
    if flow is None:
        return pd.Series(0, index=candles.index)
    f = flow.copy()
    f["ratio"] = (f.taker_buy / f.volume.replace(0, np.nan)).fillna(0.5)
    ratio = _align(candles, f, "ratio").rolling(lookback_h, min_periods=lookback_h // 2).mean()
    out = np.where(ratio > 0.5 + threshold, 1, np.where(ratio < 0.5 - threshold, -1, 0))
    return pd.Series(out, index=candles.index)


def vol_compression(data, lookback_h: int = 48, pct: float = 20) -> pd.Series:
    """+1 = volatilità compressa vs storia recente (setup pre-espansione). Mai -1."""
    c = data["candles"]
    rng = (c.high - c.low) / c.close
    cur = rng.rolling(lookback_h, min_periods=lookback_h // 2).mean()
    rank = cur.rolling(lookback_h * 10, min_periods=lookback_h * 2).rank(pct=True) * 100
    return pd.Series(np.where(rank <= pct, 1, 0), index=c.index)


SIGNALS = {
    "funding_percentile": funding_percentile,
    "range_breakout": range_breakout,
    "taker_flow": taker_flow,
    "vol_compression": vol_compression,
}
