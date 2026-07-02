"""Anti-lookahead sui segnali Coinalyze (daily con ts a INIZIO giornata).

Le barre daily Coinalyze hanno ts = 00:00 del giorno ma i valori (liquidazioni,
OI) coprono l'INTERA giornata: un merge_asof backward diretto darebbe alle
candele intraday l'aggregato del giorno ancora in corso → lookahead 24h.
Il fix shifta il lato right di +1g: il daily è usabile solo a giornata chiusa.

Proprietà testata: il segnale sulle candele del giorno D deve essere IDENTICO
con o senza la barra daily di D (il giorno in corso non può influenzare se
stesso); dal giorno D+1 la barra di D diventa visibile.
"""

import numpy as np
import pandas as pd

from backtest import signals as S

rng = np.random.default_rng(42)


def _daily(days: int) -> pd.DataFrame:
    """Storia daily con rumore, ultimo giorno estremo (squeeze short + OI in salto)."""
    ts = pd.date_range("2026-01-01", periods=days, freq="D", tz="UTC")
    liq_long = 1e6 + rng.uniform(-1e5, 1e5, days)
    liq_short = 1e6 + rng.uniform(-1e5, 1e5, days)
    oi = np.full(days, 1e9)
    liq_short[-1] = 1e8          # short liquidati in massa → imbalance estremo rialzista
    oi[-1] = 1.2e9               # OI +20% → oi_up
    return pd.DataFrame({"ts": ts, "liq_long": liq_long, "liq_short": liq_short, "oi": oi})


def _candles(start: str, hours: int) -> pd.DataFrame:
    ts = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    px = np.linspace(100, 110, hours)   # prezzo in salita → price_dir +1
    return pd.DataFrame({"ts": ts, "open": px, "high": px, "low": px,
                         "close": px, "volume": np.full(hours, 1.0)})


DAILY = _daily(30)                       # ultimo giorno: 2026-01-30 (estremo)


def _with_cache(fn, daily, candles, monkeypatch, **kw):
    sym = f"T{id(daily)}"
    monkeypatch.setitem(S._CZ_CACHE, sym, daily)
    return fn({"candles": candles, "symbol": sym}, **kw)


def test_liq_imbalance_in_day_blind(monkeypatch):
    """Candele del 30/01: stesso segnale con o senza la barra daily del 30/01."""
    c = _candles("2026-01-30 00:00", 24)
    full = _with_cache(S.liq_imbalance, DAILY, c, monkeypatch)
    trunc = _with_cache(S.liq_imbalance, DAILY.iloc[:-1], c, monkeypatch)
    pd.testing.assert_series_equal(full, trunc)


def test_liq_imbalance_visible_next_day(monkeypatch):
    """Dal 31/01 l'estremo del 30/01 è visibile: segnale +1."""
    c = _candles("2026-01-31 00:00", 24)
    sig = _with_cache(S.liq_imbalance, DAILY, c, monkeypatch)
    assert (sig == 1).all()


def test_oi_trend_in_day_blind(monkeypatch):
    c = _candles("2026-01-26 00:00", 120)    # 26-30/01: pct_change(72h) valido sul 30/01
    full = _with_cache(S.oi_trend, DAILY, c, monkeypatch)
    trunc = _with_cache(S.oi_trend, DAILY.iloc[:-1], c, monkeypatch)
    pd.testing.assert_series_equal(full, trunc)


def test_oi_trend_visible_next_day(monkeypatch):
    c = _candles("2026-01-29 00:00", 96)     # 29/01 → 01/02; pct_change(72h) valido dal 01/02
    sig = _with_cache(S.oi_trend, DAILY, c, monkeypatch)
    feb = sig[(c["ts"] >= pd.Timestamp("2026-02-01", tz="UTC")).to_numpy()]
    assert len(feb) and (feb == 1).all()


def test_bars_per_year_session_vs_24_7():
    """Annualizzazione dalla frequenza osservata: 24/7 ≈ 8760, sessione ≈ n/anni."""
    from backtest.metrics import bars_per_year
    h24 = pd.date_range("2026-01-01", periods=24 * 30, freq="h", tz="UTC")     # 30g continui
    assert abs(bars_per_year(h24) - 8760) / 8760 < 0.01
    # sessione ~6.5h/g nei giorni feriali: molto meno di 8760
    days = pd.bdate_range("2026-01-01", periods=60)
    sess = pd.DatetimeIndex([d + pd.Timedelta(hours=h) for d in days for h in range(14, 21)], tz="UTC")
    bpy = bars_per_year(sess)
    assert 1000 < bpy < 3000, bpy
