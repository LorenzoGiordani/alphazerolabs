"""Valutazione robusta: metriche per fold temporali e per regime di mercato.

Le regole sono statiche (niente fitting), quindi un run unico + slicing della
equity curve equivale al walk-forward classico, salvo posizioni a cavallo dei
confini (accettato). Il fitting arriverà con l'evoluzione: lì i fold diventano
train/test veri.

Regimi (rolling 7g sul sottostante): bull (>+8%), bear (<-8%), chop.
"""

import numpy as np
import pandas as pd

from backtest.metrics import HOURS_PER_YEAR


def regimes(candles: pd.DataFrame, window_h: int = 168, thr: float = 0.08) -> pd.Series:
    ret = candles.close.pct_change(window_h)
    return pd.Series(np.where(ret > thr, "bull", np.where(ret < -thr, "bear", "chop")),
                     index=candles.index)


def _slice_metrics(eq: pd.Series) -> dict:
    rets = eq.pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(HOURS_PER_YEAR)) if len(rets) > 1 and rets.std() > 0 else 0.0
    peak = eq.cummax()
    return {"ret": float(eq.iloc[-1] / eq.iloc[0] - 1), "sharpe": sharpe,
            "maxdd": float(((eq - peak) / peak).min()), "hours": len(eq)}


def evaluate(equity: pd.DataFrame, candles: pd.DataFrame, n_folds: int = 6) -> dict:
    """equity: df (ts, equity) dall'engine. candles: stesse candele del run."""
    eq = equity.set_index("ts").equity
    out = {"overall": _slice_metrics(eq), "folds": [], "regimes": {}}

    for chunk in np.array_split(np.arange(len(eq)), n_folds):
        if len(chunk) > 1:
            out["folds"].append(_slice_metrics(eq.iloc[chunk]))

    reg = regimes(candles)
    reg.index = candles.ts
    reg = reg.reindex(eq.index, method="ffill")
    rets = eq.pct_change().dropna()
    for name, grp in rets.groupby(reg.reindex(rets.index)):
        if len(grp) > 1:
            sharpe = float(grp.mean() / grp.std() * np.sqrt(HOURS_PER_YEAR)) if grp.std() > 0 else 0.0
            out["regimes"][name] = {"ret": float((1 + grp).prod() - 1), "sharpe": sharpe, "hours": len(grp)}

    folds_pos = sum(1 for f in out["folds"] if f["ret"] > 0)
    out["consistency"] = f"{folds_pos}/{len(out['folds'])} fold positivi"
    return out
