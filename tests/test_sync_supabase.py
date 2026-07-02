"""Test della logica di mapping journal -> righe DB (sync_supabase).

Verifica la parte difficile — non il trasporto (PostgREST) ma la trasformazione:
pairing open/close, derivazione dello status, calcolo del leverage frazionario,
deduplicazione via source_key, gestione veto. Puro Python, nessun DB.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.sync_supabase import map_records, map_lessons


def _rec(**kw):
    base = {"strategy": "agents-v1"}
    base.update(kw)
    return base


# --- open senza close = trade status 'open' ---
def test_open_without_close_is_open():
    r = [_rec(type="open", symbol="BTC", direction="long", size_usd=1000,
              entry_px=100, stop_px=95, target_px=110, opened_at="2026-01-01T10:00+00:00",
              thesis="t", logged_at="2026-01-01T10:00+00:00")]
    out = map_records(r)
    assert len(out["trades"]) == 1
    assert out["trades"][0]["status"] == "open"
    assert out["trades"][0]["risk_decision"] == "approved"


# --- open + close = trade 'closed' con pnl/reason ---
def test_open_then_close_is_closed_with_pnl():
    r = [
        _rec(type="open", symbol="BTC", direction="long", size_usd=1000,
             entry_px=100, stop_px=95, target_px=110, opened_at="2026-01-01T10:00+00:00",
             thesis="t", logged_at="2026-01-01T10:00+00:00"),
        _rec(type="close", symbol="BTC", reason="stopped", exit_px=95, pnl_usd=-50,
             ts="2026-01-01T14:00+00:00", logged_at="2026-01-01T14:00+00:00"),
    ]
    out = map_records(r)
    assert len(out["trades"]) == 1
    tr = out["trades"][0]
    assert tr["status"] == "closed"
    assert tr["pnl_usd"] == -50
    assert tr["exit_reason"] == "stopped"
    assert tr["closed_at"] is not None


# --- leverage frazionario dal sizing per rischio (not < 1x) ---
def test_leverage_is_fractional_from_equity():
    # heartbeat equity 10000, poi open size 1428 -> leverage 0.1428
    r = [
        _rec(type="heartbeat", strategy="agents-v1", equity=10000,
             logged_at="2026-01-01T09:00+00:00"),
        _rec(type="open", symbol="ZEC", direction="long", size_usd=1428,
             entry_px=433, stop_px=418, target_px=463,
             opened_at="2026-01-01T10:00+00:00", thesis="t",
             logged_at="2026-01-01T10:00+00:00"),
    ]
    tr = map_records(r)["trades"][0]
    assert abs(tr["leverage"] - 0.1428) < 0.01


# --- close senza open precedente = ignorata (non crasha) ---
def test_close_without_open_is_ignored():
    r = [_rec(type="close", symbol="BTC", reason="stopped", exit_px=95, pnl_usd=-50,
              ts="2026-01-01T14:00+00:00", logged_at="2026-01-01T14:00+00:00")]
    out = map_records(r)
    assert out["trades"] == []


# --- piu' open/close consecutivi stesso symbol: ogni close chiude l'ultima aperta ---
def test_consecutive_lifecycle_per_symbol():
    r = [
        _rec(type="open", symbol="BTC", direction="long", size_usd=1000,
             entry_px=100, stop_px=95, opened_at="2026-01-01T10:00+00:00", thesis="a",
             logged_at="2026-01-01T10:00+00:00"),
        _rec(type="close", symbol="BTC", reason="target", exit_px=110, pnl_usd=100,
             ts="2026-01-01T12:00+00:00", logged_at="2026-01-01T12:00+00:00"),
        _rec(type="open", symbol="BTC", direction="short", size_usd=800,
             entry_px=110, stop_px=115, opened_at="2026-01-01T13:00+00:00", thesis="b",
             logged_at="2026-01-01T13:00+00:00"),
        _rec(type="close", symbol="BTC", reason="stopped", exit_px=115, pnl_usd=-40,
             ts="2026-01-01T15:00+00:00", logged_at="2026-01-01T15:00+00:00"),
    ]
    tr = map_records(r)["trades"]
    assert len(tr) == 2
    by_thesis = {t["thesis"]: t for t in tr}
    assert by_thesis["a"]["pnl_usd"] == 100 and by_thesis["a"]["status"] == "closed"
    assert by_thesis["b"]["pnl_usd"] == -40 and by_thesis["b"]["status"] == "closed"


# --- source_key deterministica + unica (idempotenza) ---
def test_source_key_deterministic():
    r = [_rec(type="open", symbol="BTC", direction="long", size_usd=1000,
              entry_px=100, stop_px=95, opened_at="2026-01-01T10:00+00:00",
              thesis="t", logged_at="2026-01-01T10:00+00:00")]
    sk1 = map_records(r)["trades"][0]["source_key"]
    sk2 = map_records(r)["trades"][0]["source_key"]
    assert sk1 == sk2 == "agents-v1|BTC|2026-01-01T10:00+00:00"


# --- skip (veto/non-trade) -> tabella decisions ---
def test_skip_goes_to_decisions():
    r = [_rec(type="skip", symbol="SOL", reason="max concorrenti",
              logged_at="2026-01-01T10:00+00:00")]
    out = map_records(r)
    assert out["decisions"] and out["decisions"][0]["symbol"] == "SOL"
    assert out["trades"] == []


# --- heartbeat -> equity_snapshots ---
def test_heartbeat_to_snapshots():
    r = [_rec(type="heartbeat", strategy="tsmom-v1", equity=10350.5,
              open_positions=[{"sym": "BTC"}], logged_at="2026-01-01T10:00+00:00")]
    snap = map_records(r)["equity_snapshots"]
    assert len(snap) == 1
    assert snap[0]["strategy"] == "tsmom-v1"
    assert abs(snap[0]["equity_usd"] - 10350.5) < 1e-6


# --- lessons: mapping + tags array ---
def test_lessons_mapping():
    r = [{"trade_key": "agents-v1|ZEC|2026-06-11", "symbol": "ZEC", "strategy": "agents-v1",
          "pnl_usd": -50.92, "verdict": "thesis_wrong", "lesson": "fade crowding senza conferma",
          "tags": ["funding", "squeeze"], "logged_at": "2026-06-12T07:00+00:00"}]
    rows = map_lessons(r)
    assert len(rows) == 1
    assert rows[0]["lesson"] == "fade crowding senza conferma"
    assert rows[0]["tags"] == ["funding", "squeeze"]
    assert rows[0]["verdict"] == "thesis_wrong"


def test_upsert_isolates_bad_rows(monkeypatch):
    """Chunk che fallisce → retry riga-per-riga: la riga marcia non blocca le altre."""
    import scripts.sync_supabase as ss

    class R:
        def __init__(self, code, text=""):
            self.status_code, self.text = code, text

    def fake_post(url, h, table, rows):
        if any(r["source_key"] == "bad" for r in rows):
            return R(400, "violates check constraint")
        return R(201)

    monkeypatch.setattr(ss, "_post", fake_post)
    rows = [{"source_key": f"r{i}"} for i in range(5)] + [{"source_key": "bad"}]
    ok, failed, msg = ss._upsert("http://x", {}, "trades", rows)
    assert ok == 5 and failed == 1
    assert "bad" in msg


def test_upsert_all_good_single_chunk(monkeypatch):
    import scripts.sync_supabase as ss
    calls = []

    def fake_post(url, h, table, rows):
        calls.append(len(rows))
        class R: status_code, text = 201, ""
        return R()

    monkeypatch.setattr(ss, "_post", fake_post)
    rows = [{"source_key": f"r{i}"} for i in range(1200)]
    ok, failed, msg = ss._upsert("http://x", {}, "trades", rows)
    assert ok == 1200 and failed == 0 and msg == "ok"
    assert calls == [500, 500, 200]     # chunking rispettato
