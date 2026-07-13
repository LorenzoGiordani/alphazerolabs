import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_live_cache_reuses_only_sufficient_lookback(tmp_path, monkeypatch):
    import pipeline.live as live

    calls = []

    def fetch(symbol, lookback_h=1000):
        calls.append((symbol, lookback_h))
        return {"symbol": symbol, "lookback_h": lookback_h}

    monkeypatch.setattr(live, "_LIVE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(live, "fetch_live", fetch)
    monkeypatch.setattr(live.time, "time", lambda: 123_456)

    assert live.fetch_live_cached("BTC", 100)["lookback_h"] == 100
    assert live.fetch_live_cached("BTC", 50)["lookback_h"] == 100
    assert live.fetch_live_cached("BTC", 200)["lookback_h"] == 200
    assert calls == [("BTC", 100), ("BTC", 200)]


def test_hyperliquid_retry_is_bounded(monkeypatch):
    import pipeline.live as live

    class Response:
        def __init__(self, status, payload):
            self.status_code = status
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    responses = iter([Response(429, {}), Response(200, {"ok": True})])
    sleeps = []
    monkeypatch.setattr(live.requests, "post", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(live.time, "sleep", sleeps.append)
    assert live._hl_post({"type": "test"}) == {"ok": True}
    assert sleeps == [1]


def test_live_cache_key_keeps_legacy_and_hip3_symbols_distinct(tmp_path, monkeypatch):
    import pipeline.live as live

    calls = []

    def fetch(symbol, lookback_h=1000):
        calls.append(symbol)
        return {"source_symbol": symbol}

    monkeypatch.setattr(live, "_LIVE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(live, "fetch_live", fetch)
    monkeypatch.setattr(live.time, "time", lambda: 123_456)
    assert live.fetch_live_cached("xyz_CL")["source_symbol"] == "xyz_CL"
    assert live.fetch_live_cached("xyz:CL")["source_symbol"] == "xyz:CL"
    assert calls == ["xyz_CL", "xyz:CL"]


def test_portfolio_candle_cache_never_fetches_funding(tmp_path, monkeypatch):
    import pipeline.live as live

    calls = []

    def fetch(symbol, lookback_h, *, include_funding=True):
        calls.append((symbol, lookback_h, include_funding))
        return {"candles": [], "funding": None}

    monkeypatch.setattr(live, "_LIVE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(live, "_fetch_hl", fetch)
    monkeypatch.setattr(live.time, "time", lambda: 123_456)
    live.fetch_candles_cached("BTC", 341)
    live.fetch_candles_cached("BTC", 100)
    assert calls == [("BTC", 341, False)]


def test_hyperliquid_stale_candles_fail_closed(monkeypatch):
    import pipeline.live as live

    now_s = 2_000_000_000
    old_ms = (now_s - 5 * 3600) * 1000
    rows = [
        {"t": old_ms - 3_600_000, "o": "1", "h": "2", "l": "1", "c": "1.5", "v": "10"},
        {"t": old_ms, "o": "1.5", "h": "2", "l": "1", "c": "1.6", "v": "11"},
    ]
    monkeypatch.setattr(live.time, "time", lambda: now_s)
    monkeypatch.setattr(live, "_hl_post", lambda *_args, **_kwargs: rows)
    with pytest.raises(RuntimeError, match="candele stale/future"):
        live._fetch_hl("BTC", 10, include_funding=False)
