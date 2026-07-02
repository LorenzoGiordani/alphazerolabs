"""Metriche di performance su equity curve oraria."""

import numpy as np
import pandas as pd

HOURS_PER_YEAR = 24 * 365


def bars_per_year(ts) -> float:
    """Frequenza annua osservata delle barre dalla serie timestamp.
    Crypto 24/7 ≈ 8760; asset HIP-3 a sessione ≈ 1600: annualizzare con √8760
    fisso gonfierebbe lo Sharpe fino a 2.3× sulle commodities."""
    t = pd.to_datetime(pd.Series(list(ts)), utc=True)
    n = len(t) - 1
    if n < 1:
        return float(HOURS_PER_YEAR)
    span_y = (t.iloc[-1] - t.iloc[0]).total_seconds() / (365.0 * 24 * 3600)
    return n / span_y if span_y > 0 else float(HOURS_PER_YEAR)


def compute(equity: pd.DataFrame, trades: list) -> dict:
    eq = equity.equity
    rets = eq.pct_change().dropna()
    total_return = eq.iloc[-1] / eq.iloc[0] - 1

    sharpe = 0.0
    if len(rets) > 1 and rets.std() > 0:
        sharpe = float(rets.mean() / rets.std() * np.sqrt(bars_per_year(equity.ts)))

    peak = eq.cummax()
    max_dd = float(((eq - peak) / peak).min())

    pnls = [t["pnl_usd"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls) if pnls else 0.0
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")

    return {
        "total_return": float(total_return),
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "n_trades": len(pnls),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
    }


def buy_and_hold(candles: pd.DataFrame) -> dict:
    """Baseline obbligatoria: long 1x dall'inizio alla fine, stessa finestra."""
    eq = pd.DataFrame({"ts": candles.ts, "equity": candles.close / candles.close.iloc[0]})
    return compute(eq, [])


def report(name: str, m: dict) -> str:
    return (f"{name:<22} ret {m['total_return']:+7.2%} | sharpe {m['sharpe']:5.2f} | "
            f"maxDD {m['max_drawdown']:7.2%} | trades {m['n_trades']:>4} | "
            f"win {m['win_rate']:.0%} | PF {m['profit_factor']:.2f}")
