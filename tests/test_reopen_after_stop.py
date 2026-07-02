"""Niente riapertura incondizionata dopo uno stop dell'engine.

Prima del fix: dopo stop/target/liquidazione il callback di compile_strategy
non lo sapeva (state["dir"] restava settato solo fino al time stop) e l'engine
riapriva alla barra successiva sullo stesso segnale persistente → il backtest
per-simbolo misurava "always-in", non il segnale.

Ora l'engine passa l'esposizione corrente al callback: engine flat + state
aperto = chiusura engine → cooldown finché fire non si spegne e riaccende.
"""

import numpy as np
import pandas as pd

from backtest import signals as S
from backtest.engine import Backtest
from backtest.strategy import compile_strategy


def _candles(closes):
    px = np.asarray(closes, dtype=float)
    n = len(px)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
        "open": px, "high": px * 1.001, "low": px * 0.999,
        "close": px, "volume": np.full(n, 1e6)})


SPEC = {
    "id": "test-reopen-v1",
    "signals": [{"name": "always_long", "params": {}}],
    "entry": {"rule": "always_long", "direction": "follow:always_long"},
    "risk": {"risk_per_trade_pct": 1.0, "max_leverage": 2.0},
    "exit": {"stop_pct": 5.0, "time_stop_h": 10_000},  # stop 5%, niente time stop di fatto
}


def _run(closes, sig_values, monkeypatch):
    monkeypatch.setitem(
        S.SIGNALS, "always_long",
        lambda data, **kw: pd.Series(sig_values, index=data["candles"].index))
    c = _candles(closes)
    strat, _ = compile_strategy(SPEC, {"candles": c, "symbol": None})
    bt = Backtest(c, fee=0.0, slippage=0.0, funding_hourly=0.0)
    bt.run(strat)
    return bt.trades


def test_no_reopen_while_signal_persists(monkeypatch):
    """Due crolli oltre lo stop, segnale SEMPRE attivo: solo il primo stop scatta
    (niente riapertura → il secondo crollo non produce trade)."""
    closes = [100.0] * 5 + [80.0] * 20 + [60.0] * 20
    trades = _run(closes, [1] * 45, monkeypatch)
    assert [t["reason"] for t in trades] == ["stopped"], \
        f"attesi 1 solo stop senza riaperture, avuti: {[(str(t['ts']), t['reason']) for t in trades]}"


def test_reopen_after_signal_refires(monkeypatch):
    """Il segnale si SPEGNE e si riaccende tra i due crolli: il rientro è permesso
    e il secondo crollo produce il secondo stop."""
    sig = [1] * 20 + [0] * 5 + [1] * 20          # off ai bar 20-24, poi refire
    closes = [100.0] * 5 + [80.0] * 20 + [80.0] * 5 + [60.0] * 15
    trades = _run(closes, sig, monkeypatch)
    stops = [t for t in trades if t["reason"] == "stopped"]
    assert len(stops) == 2, \
        f"attesi 2 stop (uno per crollo, rientro dopo refire), avuti: {[(str(t['ts']), t['reason']) for t in trades]}"
