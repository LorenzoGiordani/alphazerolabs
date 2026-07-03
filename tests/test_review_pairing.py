"""Test: review.pending() accoppia ogni close all'open cronologicamente giusto.

Bug originale: pre-scan che teneva solo l'ultimo open per (strategy, symbol) →
su trade ripetuti il post-mortem del primo trade leggeva la tesi del secondo.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scripts.review as review


def _setup(tmp_path, monkeypatch, rows):
    jf = tmp_path / "journal.jsonl"
    jf.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(review, "JOURNAL", jf)
    monkeypatch.setattr(review, "LESSONS", tmp_path / "lessons.jsonl")


def test_repeated_trades_pair_with_own_open(tmp_path, monkeypatch):
    rows = [
        {"type": "open", "strategy": "s1", "symbol": "BTC", "thesis": "tesi A",
         "opened_at": "2026-01-01T00:00"},
        {"type": "close", "strategy": "s1", "symbol": "BTC", "ts": "2026-01-02T00:00",
         "pnl_usd": -10, "reason": "stop"},
        {"type": "open", "strategy": "s1", "symbol": "BTC", "thesis": "tesi B",
         "opened_at": "2026-01-03T00:00"},
        {"type": "close", "strategy": "s1", "symbol": "BTC", "ts": "2026-01-04T00:00",
         "pnl_usd": 20, "reason": "target"},
    ]
    _setup(tmp_path, monkeypatch, rows)
    todo = review.pending()
    assert len(todo) == 2
    assert todo[0]["open"]["thesis"] == "tesi A"   # bug: leggeva "tesi B"
    assert todo[1]["open"]["thesis"] == "tesi B"


def test_partial_closes_share_same_open(tmp_path, monkeypatch):
    rows = [
        {"type": "open", "strategy": "s1", "symbol": "ETH", "thesis": "tesi X",
         "opened_at": "2026-01-01T00:00"},
        {"type": "close", "strategy": "s1", "symbol": "ETH", "ts": "2026-01-02T00:00",
         "pnl_usd": 5, "reason": "partial", "frac": 0.5, "remaining": 0.5},
        {"type": "close", "strategy": "s1", "symbol": "ETH", "ts": "2026-01-03T00:00",
         "pnl_usd": 5, "reason": "target", "frac": 0.5, "remaining": 0.0},
    ]
    _setup(tmp_path, monkeypatch, rows)
    todo = review.pending()
    assert len(todo) == 2
    assert all(t["open"]["thesis"] == "tesi X" for t in todo)


def test_close_without_prior_open_gets_empty(tmp_path, monkeypatch):
    rows = [
        {"type": "close", "strategy": "s1", "symbol": "SOL", "ts": "2026-01-02T00:00",
         "pnl_usd": 1, "reason": "stop"},
        {"type": "open", "strategy": "s1", "symbol": "SOL", "thesis": "dopo",
         "opened_at": "2026-01-03T00:00"},
    ]
    _setup(tmp_path, monkeypatch, rows)
    todo = review.pending()
    assert len(todo) == 1
    assert todo[0]["open"] == {}   # niente open precedente: non inventare tesi
