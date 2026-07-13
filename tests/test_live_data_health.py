import sys
from pathlib import Path

import requests
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import live


class Response:
    def __init__(self, status, data=None, headers=None):
        self.status_code = status
        self._data = data
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


def test_hl_post_retries_only_retryable_statuses(monkeypatch):
    replies = [Response(429, headers={"Retry-After": "0"}), Response(503), Response(200, [])]
    sleeps = []
    monkeypatch.setattr(live.requests, "post", lambda *a, **k: replies.pop(0))
    monkeypatch.setattr(live.time, "sleep", sleeps.append)

    assert live._hl_post({"type": "candleSnapshot"}) == []
    assert sleeps == [0.0, 0.5]

    calls = []
    monkeypatch.setattr(live.requests, "post", lambda *a, **k: calls.append(1) or Response(400))
    with pytest.raises(RuntimeError, match=r"candleSnapshot: HTTP 400"):
        live._hl_post({"type": "candleSnapshot"})
    assert len(calls) == 1


def test_hl_post_reports_invalid_json_with_type_and_status(monkeypatch):
    monkeypatch.setattr(
        live.requests, "post", lambda *a, **k: Response(200, ValueError("bad json"))
    )
    with pytest.raises(RuntimeError, match=r"perpDexs: invalid JSON \(HTTP 200\)"):
        live._hl_post({"type": "perpDexs"})


def test_perp_market_snapshot_is_qualified_and_complete(monkeypatch):
    def post(payload, timeout=30):
        if payload["type"] == "perpDexs":
            return [None, {"name": "xyz"}]
        dex = payload["dex"]
        asset = {
            "name": "BTC" if not dex else "GOLD",
            "maxLeverage": 40 if not dex else 10,
        }
        context = {
            "markPx": "110",
            "prevDayPx": "100",
            "dayNtlVlm": "2000000",
            "openInterest": "50",
            "funding": "0.0001",
        }
        return [{"universe": [asset]}, [context]]

    monkeypatch.setattr(live, "_hl_post", post)
    rows = live.perp_market_snapshot()

    assert [row["symbol"] for row in rows] == ["BTC", "xyz:GOLD"]
    assert rows[1] == {
        "symbol": "xyz:GOLD",
        "dex": "xyz",
        "delisted": False,
        "mark": 110.0,
        "prev_day_px": 100.0,
        "change_24h": pytest.approx(0.1),
        "volume_24h_usd": 2_000_000.0,
        "open_interest_usd": 5_500.0,
        "funding": 0.0001,
        "max_leverage": 10.0,
    }


def test_perp_market_snapshot_fails_closed_on_one_bad_dex(monkeypatch):
    def post(payload, timeout=30):
        if payload["type"] == "perpDexs":
            return [{"name": "bad"}]
        if not payload["dex"]:
            return [{"universe": []}, []]
        return [{"universe": [{"name": "X"}]}, []]

    monkeypatch.setattr(live, "_hl_post", post)
    with pytest.raises(RuntimeError, match="universe/context mismatch"):
        live.perp_market_snapshot()


def test_fetch_live_cache_keys_lookback_and_funding_and_writes_atomically(monkeypatch, tmp_path):
    calls = []

    def fetch(symbol, lookback_h=1000, with_funding=True):
        calls.append((symbol, lookback_h, with_funding))
        return {"symbol": symbol, "lookback": lookback_h, "funding": with_funding}

    monkeypatch.setattr(live, "_LIVE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(live, "fetch_live", fetch)
    monkeypatch.setattr(live.time, "time", lambda: 7_200)

    first = live.fetch_live_cached("xyz:GOLD", 10, with_funding=False)
    assert live.fetch_live_cached("xyz:GOLD", 10, with_funding=False) == first
    live.fetch_live_cached("xyz:GOLD", 11, with_funding=False)
    live.fetch_live_cached("xyz:GOLD", 11, with_funding=True)

    assert calls == [
        ("xyz:GOLD", 10, False),
        ("xyz:GOLD", 11, False),
        ("xyz:GOLD", 11, True),
    ]
    assert len(list(tmp_path.glob("*.pkl"))) == 3
    assert not list(tmp_path.glob("*.tmp"))


def test_fetch_hl_can_skip_funding_and_never_masks_funding_errors(monkeypatch):
    candles = [
        {"t": 1_000, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "10"},
        {"t": 2_000, "o": "1.5", "h": "2", "l": "1", "c": "1.8", "v": "12"},
    ]
    calls = []

    def candles_only(payload, timeout=30):
        calls.append(payload["type"])
        return candles

    monkeypatch.setattr(live, "_hl_post", candles_only)
    data = live._fetch_hl("BTC", 10, with_funding=False)
    assert data["symbol"] == "BTC"
    assert data["funding"] is None
    assert calls == ["candleSnapshot"]

    def funding_fails(payload, timeout=30):
        if payload["type"] == "candleSnapshot":
            return candles
        raise RuntimeError("HL fundingHistory: HTTP 503")

    monkeypatch.setattr(live, "_hl_post", funding_fails)
    with pytest.raises(RuntimeError, match=r"fundingHistory: HTTP 503"):
        live._fetch_hl("BTC", 10)
