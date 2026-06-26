"""Test del modello di market impact square-root (slippage size-aware).

Verifica le proprieta' oneste dell'implementazione: additivita' (mai sotto il
base), scala con la size, anti-lookahead, e identicita' al legacy quando
disabilitato (backward-compatibilita').
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import Backtest, _liquidity_arrays


def _candles(n: int = 300, base: float = 100.0, vol: float = 50.0,
             ret_std: float = 0.008) -> pd.DataFrame:
    """Candele sintetiche. vol = volume in valuta base; ret_std = std del
    log-rendimento orario (default 0.008 ≈ σ_d 3.9%, realistico crypto)."""
    ts = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    rng = np.random.default_rng(0)
    logret = rng.normal(0, ret_std, n)
    logret[0] = 0.0
    close = base * np.exp(np.cumsum(logret))
    return pd.DataFrame({"ts": ts, "open": close, "high": close, "low": close,
                         "close": close, "volume": [vol] * n})


def _strat_long(expo=1.0):
    def f(_):
        return {"exposure": expo, "stop_pct": 50.0, "exit_cfg": {"max_leverage": 1.0}}
    return f


# --- backward-compat: impact None == slippage fisso legacy, curve identiche ---
def test_disabled_identical_to_legacy():
    c = _candles()
    eq_off = Backtest(c, impact_k=None).run(_strat_long())
    # riproduciamo la run legacy "a mano" stesso oggetto: basta confrontare che
    # abilitare con k=0 dia slippage == base -> identico a disabilitato
    eq_k0 = Backtest(c, impact_k=0.0).run(_strat_long())
    pd.testing.assert_series_equal(
        eq_off["equity"].reset_index(drop=True),
        eq_k0["equity"].reset_index(drop=True),
        check_names=False)


# --- additivo: lo slippage effettivo non scende MAI sotto il base ---
def test_slippage_never_below_base():
    c = _candles(vol=10.0)  # poco liquido
    bt = Backtest(c, impact_k=0.5, impact_window_h=24)
    bt.run(_strat_long(1.0))  # inizializza gli array
    # campiona su barre calde (dopo warmup)
    for i in range(50, len(c)):
        slip = bt._effective_slippage(i, notional_usd=10_000.0)
        assert slip >= bt.slippage - 1e-12, f"slip {slip} < base {bt.slippage} a barra {i}"


# --- monotonico nella size: notionale piu' grande => slippage >= ---
def test_slippage_scales_with_size():
    c = _candles()
    bt = Backtest(c, impact_k=0.5, impact_window_h=24)
    bt.run(_strat_long())
    i = len(c) // 2
    small = bt._effective_slippage(i, notional_usd=1_000.0)
    big = bt._effective_slippage(i, notional_usd=1_000_000.0)
    assert big >= small, "slippage deve crescere (o restare) col notionale"


# --- liquidita' alta (scala BTC) + size piccola => impact ~ nullo, slip ~ base ---
def test_impact_negligible_on_liquid_small_size():
    c = _candles(vol=10_000_000.0)  # V≈$1e9/barra (scala BTC), σ_h realistica
    bt = Backtest(c, impact_k=0.5, impact_window_h=24)
    bt.run(_strat_long())
    i = len(c) // 2
    slip = bt._effective_slippage(i, notional_usd=10_000.0)
    # $10k su liquidita' BTC-scale: impact trascurabile (<0.5 bps sopra il base)
    assert slip < bt.slippage + 0.00005


# --- illiquido + volatile + size grande => impact sostanziale, slip >> base ---
def test_impact_substantial_on_illiquid_large_size():
    # ADV basso (~5*100=500 USD/barra), volatilita' crypto-like (σ_d≈3.9%)
    c = _candles(vol=5.0, ret_std=0.008)
    bt = Backtest(c, impact_k=0.5, impact_window_h=24)
    bt.run(_strat_long())
    i = len(c) // 2
    slip = bt._effective_slippage(i, notional_usd=50_000.0)
    # participation saturato a 1.0; impact = 0.5·σ_d ≈ 0.5·0.039 ≈ 200 bps
    assert slip > bt.slippage * 10, f"impact atteso sostanziale, slip={slip}"


# --- anti-lookahead: ADV/sigma alla barra i non dipendono da barre future ---
def test_liquidity_arrays_no_lookahead():
    c = _candles()
    adv1, sig1 = _liquidity_arrays(c, window_h=24)
    # modifica il volume di barre FUTURE e verifica che i valori passati non cambino
    i = 100
    c2 = c.copy()
    c2.loc[i + 50:, "volume"] = 9999.0  # sporco il futuro
    adv2, sig2 = _liquidity_arrays(c2, window_h=24)
    np.testing.assert_allclose(adv1[:i + 1], adv2[:i + 1], err_msg="ADV lookahead!")
    np.testing.assert_allclose(sig1[:i + 1], sig2[:i + 1], err_msg="sigma lookahead!")


# --- end-to-end: su asset liquido l'impact acceso muove poco l'equity ---
def test_endtoend_liquid_small_drag():
    c = _candles(vol=10_000.0, base=100.0)
    eq_off = Backtest(c, impact_k=None).run(_strat_long())
    eq_on = Backtest(c, impact_k=0.5).run(_strat_long())
    # su asset liquido la differenza finale e' piccola (<0.5% dell'equity)
    assert abs(eq_on["equity"].iloc[-1] - eq_off["equity"].iloc[-1]) < 50.0
