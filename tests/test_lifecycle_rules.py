"""Test di paper_stats (basket Sharpe per-asset) e validate_spec_risk (regole 3, 5)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.lifecycle import GLOBAL_RISK_CAPS, paper_stats, validate_spec_risk


def _write_journal(tmp_path: Path, rows: list[dict]) -> None:
    """Scrive un journal.jsonl fittizio nel tmp_path e patcha lifecycle.JOURNAL."""
    import backtest.lifecycle as lc
    jf = tmp_path / "journal.jsonl"
    jf.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    lc.JOURNAL = jf


def _write_state(tmp_path: Path, strat: str, equity: float) -> None:
    import backtest.lifecycle as lc
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir(exist_ok=True)
    sf = paper_dir / "state.json"
    sf.write_text(json.dumps({strat: {"equity": equity}}))
    lc.ROOT = tmp_path


def _trade(strategy: str, sym: str, pnl: float, stop_pct: float = 0.04) -> dict:
    """Genera open+close pair per un trade con R-multiple derivato."""
    entry = 100.0
    size = 1000.0
    return [
        {"type": "open", "strategy": strategy, "symbol": sym,
         "entry_px": entry, "stop_px": entry * (1 - stop_pct), "size_usd": size},
        {"type": "close", "strategy": strategy, "symbol": sym,
         "exit_px": entry + (pnl / size) * entry, "pnl_usd": pnl},
    ]


def test_paper_stats_basket_mean_r(tmp_path, monkeypatch):
    """basket_mean_r = mean dei mean-R per-asset. Con trade count diseguali
    tra simboli, pooled e basket divergono (basket penalizza concentrazione)."""
    rows = []
    # BTC: 3 trade, tutti +100 → mean_r = 2.5
    for _ in range(3):
        rows += _trade("test-strat", "BTC", 100)
    # ZEC: 1 trade -50 → mean_r = -1.25
    rows += _trade("test-strat", "ZEC", -50)
    _write_journal(tmp_path, rows)
    monkeypatch.setattr("backtest.lifecycle.JOURNAL", tmp_path / "journal.jsonl")
    monkeypatch.setattr("backtest.lifecycle.ROOT", tmp_path)
    st = paper_stats("test-strat")
    # pooled: (3*2.5 + 1*(-1.25)) / 4 = 1.5625 → pooled mean_r alto
    assert st["mean_r"] > 1.5
    # basket: (2.5 + (-1.25)) / 2 = 0.625 → basket più basso
    assert st["basket_mean_r"] < 0.7
    assert st["basket_mean_r"] < st["mean_r"]  # concentrazione penalizzata
    assert st["symbols_traded"] == 2


def test_paper_stats_basket_concentration_penalty(tmp_path, monkeypatch):
    """Strategia che vince su 1 asset con molti trade e perde su 1 con pochi:
    pooled mean_r > basket_mean_r (concentrazione mascherata dal pooled)."""
    rows = []
    # BTC: 10 trade +50 → mean_r = 1.25 (dominante nel pooled)
    for _ in range(10):
        rows += _trade("test-strat", "BTC", 50)
    # ZEC: 1 trade -40 → mean_r = -1.0
    rows += _trade("test-strat", "ZEC", -40)
    _write_journal(tmp_path, rows)
    monkeypatch.setattr("backtest.lifecycle.JOURNAL", tmp_path / "journal.jsonl")
    monkeypatch.setattr("backtest.lifecycle.ROOT", tmp_path)
    st = paper_stats("test-strat")
    # pooled: (10*1.25 + 1*(-1)) / 11 = 1.045 → positivo
    assert st["mean_r"] > 1.0
    # basket: (1.25 + (-1.0)) / 2 = 0.125 → molto più basso
    assert st["basket_mean_r"] < 0.2
    assert st["basket_mean_r"] < st["mean_r"]  # concentrazione penalizzata
    assert st["symbols_traded"] == 2


def test_paper_stats_basket_sharpe_sd_near_zero(tmp_path, monkeypatch):
    """R quasi identici (sd≈0 ma non 0 per rounding float): la t-stat per-symbol
    non deve esplodere e dominare la media del basket (epsilon + clamp ±20)."""
    rows = []
    rows += _trade("test-strat", "BTC", 50.0)
    rows += _trade("test-strat", "BTC", 50.0 + 1e-7)   # sd ~ 1e-12
    # secondo simbolo con sd sana, per verificare che la media resti sensata
    rows += _trade("test-strat", "ETH", 40.0)
    rows += _trade("test-strat", "ETH", 60.0)
    _write_journal(tmp_path, rows)
    monkeypatch.setattr("backtest.lifecycle.JOURNAL", tmp_path / "journal.jsonl")
    monkeypatch.setattr("backtest.lifecycle.ROOT", tmp_path)
    st = paper_stats("test-strat")
    assert abs(st["basket_sharpe_r"]) <= 20.0


def test_paper_stats_equity_dd_pct(tmp_path, monkeypatch):
    """equity_dd_pct legge da state.json (regola P1-b)."""
    rows = []
    rows += _trade("test-strat", "BTC", 100)
    _write_journal(tmp_path, rows)
    _write_state(tmp_path, "test-strat", 8200.0)  # -18%
    monkeypatch.setattr("backtest.lifecycle.JOURNAL", tmp_path / "journal.jsonl")
    monkeypatch.setattr("backtest.lifecycle.ROOT", tmp_path)
    st = paper_stats("test-strat")
    assert st["equity_dd_pct"] == -18.0


def test_paper_stats_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("backtest.lifecycle.JOURNAL", tmp_path / "journal.jsonl")
    monkeypatch.setattr("backtest.lifecycle.ROOT", tmp_path)
    (tmp_path / "journal.jsonl").write_text("")
    st = paper_stats("nonexistent")
    assert st["n_closed"] == 0
    assert st["basket_mean_r"] == 0.0
    assert st["basket_sharpe_r"] == 0.0
    assert st["symbols_traded"] == 0


def test_validate_spec_risk_ok():
    """Spec entro i caps → nessun warning."""
    spec = {"id": "test-ok", "risk": {"max_leverage": 2, "max_concurrent_positions": 5,
                                       "risk_per_trade_pct": 1.0}}
    assert validate_spec_risk(spec) == []


def test_validate_spec_risk_leverage_exceeds():
    spec = {"id": "test-bad", "risk": {"max_leverage": 6, "max_concurrent_positions": 3,
                                        "risk_per_trade_pct": 1.0}}
    warns = validate_spec_risk(spec)
    assert any("max_leverage 6" in w for w in warns)


def test_validate_spec_risk_concurrent_exceeds():
    spec = {"id": "test-bad", "risk": {"max_leverage": 2, "max_concurrent_positions": 20,
                                        "risk_per_trade_pct": 1.0}}
    warns = validate_spec_risk(spec)
    assert any("max_concurrent_positions 20" in w for w in warns)


def test_validate_spec_risk_by_class_override_flagged():
    """by_class.max_leverage > cap è flaggato (consentito ma surfaced)."""
    spec = {"id": "test-cls", "risk": {"max_leverage": 2, "max_concurrent_positions": 3,
                                        "risk_per_trade_pct": 1.0},
            "exit": {"by_class": {"stock": {"max_leverage": 5, "target_r": 1.8}}}}
    warns = validate_spec_risk(spec)
    assert any("by_class.stock.max_leverage 5" in w for w in warns)


def test_validate_spec_risk_missing_block():
    spec = {"id": "test-missing"}
    warns = validate_spec_risk(spec)
    assert any("risk mancante" in w for w in warns)


def test_global_caps_sane():
    """I caps globali non devono essere assurdi — sanity check del config."""
    assert GLOBAL_RISK_CAPS["max_leverage"] >= 2   # almeno quanto desk LLM
    assert GLOBAL_RISK_CAPS["max_concurrent_positions"] >= 3
    assert 0 < GLOBAL_RISK_CAPS["max_risk_per_trade_pct"] <= 5


def test_complexity_penalty_simple():
    """Strategia con 1 segnale + 2 params = penalty bassa (base gratuita)."""
    from scripts.evolve import complexity_penalty
    spec = {"signals": [{"name": "tsmom", "params": {"short_h": 168, "long_h": 720}}]}
    # 1 segnale = 0 (base gratis), 2 params = 0.01 → 0.01
    assert complexity_penalty(spec) == 0.01


def test_complexity_penalty_grows_with_signals():
    """Più segnali = penalty più alta (overfitting risk cresce)."""
    from scripts.evolve import complexity_penalty
    simple = {"signals": [{"name": "tsmom", "params": {"short_h": 168, "long_h": 720}}]}
    complex_spec = {"signals": [
        {"name": "tsmom", "params": {"short_h": 168, "long_h": 720}},
        {"name": "liq_imbalance", "params": {"lookback_d": 21, "extreme_pct": 80}},
        {"name": "kronos_forecast", "params": {"horizon_h": 24, "min_move_pct": 1.0}},
        {"name": "news_event", "params": {"max_age_h": 24, "min_z": 2.0}},
    ]}
    assert complexity_penalty(complex_spec) > complexity_penalty(simple)
    # complex: 3 extra signals * 0.02 + 8 params * 0.005 = 0.06 + 0.04 = 0.10
    assert complexity_penalty(complex_spec) == 0.10


def test_complexity_penalty_by_class_counts():
    """by_class exit params contano (override per-asset-class = gradi extra)."""
    from scripts.evolve import complexity_penalty
    spec = {"signals": [{"name": "tsmom", "params": {"short_h": 168}}],
            "exit": {"by_class": {"crypto": {"stop_atr_mult": 2.5, "target_r": 2.0},
                                   "stock": {"max_leverage": 4}}}}
    # 0 extra signals + 1 param signal + 3 by_class params = 0.005 + 0.015 = 0.02
    assert complexity_penalty(spec) == 0.02


def test_append_lesson_unified_channel(tmp_path, monkeypatch):
    """promote.add_lesson scrive via review.append_lesson (regola 7, canale unificato)."""
    import backtest.lifecycle as lc
    lc.ROOT = tmp_path
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir(exist_ok=True)
    monkeypatch.setattr("scripts.review.LESSONS", paper_dir / "lessons.jsonl")
    monkeypatch.setattr("backtest.lifecycle.ROOT", tmp_path)
    from scripts.review import append_lesson
    rec = {"trade_key": "lifecycle|test-strat|2026-06-24",
           "symbol": "basket", "strategy": "test-strat",
           "verdict": "thesis_wrong", "lesson": "test lesson", "tags": ["test"]}
    append_lesson(rec)
    lines = (paper_dir / "lessons.jsonl").read_text().splitlines()
    assert len(lines) == 1
    written = json.loads(lines[0])
    assert written["lesson"] == "test lesson"
    assert "logged_at" in written   # append_lesson aggiunge timestamp


def test_promote_dsr_gate_blocks_overfit(tmp_path, monkeypatch):
    """promote.py non promuove challenger con DSR < MIN_DSR anche se basket_sharpe alto."""
    import backtest.lifecycle as lc
    lc.ROOT = tmp_path
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir(exist_ok=True)
    monkeypatch.setattr("backtest.lifecycle.ROOT", tmp_path)
    monkeypatch.setattr("backtest.lifecycle.JOURNAL", paper_dir / "journal.jsonl")
    # spec fittizio con DSR basso salvato nel backtest
    from backtest.lifecycle import backtest_dsr
    spec = {"backtest": {"basket_6m": {"aggregate": {"dsr": 0.50}}}}
    assert backtest_dsr(spec) == 0.50
    # DSR 0.50 < MIN_DSR 0.95 → gate deve bloccare (verificato nella logica promote)


def test_paper_exits_closes_retired_positions(tmp_path, monkeypatch):
    """paper_exits chiude le posizioni delle strategie retired al prezzo attuale."""
    import scripts.paper_exits as pe
    import scripts.paper_trade as pt

    paper_dir = tmp_path / "paper"
    paper_dir.mkdir(exist_ok=True)
    state_file = paper_dir / "state.json"
    journal_file = paper_dir / "journal.jsonl"

    # stato con una strategia retired (tsmom-v1) con una posizione aperta
    state = {
        "tsmom-v1": {
            "equity": 9800.0,
            "positions": {
                "BTC": {
                    "strategy": "tsmom-v1", "symbol": "BTC", "direction": "long",
                    "entry_px": 70000.0, "stop_px": 67000.0, "target_px": 76000.0,
                    "size_usd": 1000.0, "sign": 1, "remaining": 1.0,
                    "checked_until": "2026-06-24 00:00", "opened_at": "2026-06-20 00:00",
                }
            },
        }
    }
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(pe, "STATE_FILE", state_file)
    monkeypatch.setattr(pt, "STATE_FILE", state_file)
    monkeypatch.setattr(pt, "JOURNAL", journal_file)

    # all_specs ritorna tsmom-v1 con status retired
    monkeypatch.setattr(
        "scripts.paper_exits.all_specs",
        lambda: [(tmp_path / "tsmom-v1.yaml", {"id": "tsmom-v1", "status": "retired"})]
    )

    # fetch_live ritorna candele fittizie con close=72000 (long in profitto)
    import pandas as pd
    candles = pd.DataFrame({"ts": pd.to_datetime(["2026-06-24 12:00"]), "close": [72000.0],
                            "high": [72500.0], "low": [71500.0], "open": [71800.0]})
    monkeypatch.setattr("scripts.paper_exits.fetch_live",
                        lambda sym: {"candles": candles, "forming": None})

    pe.main()

    new_state = json.loads(state_file.read_text())
    assert "BTC" not in new_state["tsmom-v1"]["positions"], "posizione retired non chiusa"
    # equity deve riflettere il PnL realizzato (+fee)
    assert new_state["tsmom-v1"]["equity"] > 9800.0, "PnL long in profitto non accreditato"
    # journal deve avere l'evento close con reason=retired
    close_events = [json.loads(l) for l in journal_file.read_text().splitlines()
                    if json.loads(l).get("type") == "close"]
    assert any(e.get("reason") == "retired" for e in close_events), "reason=retired non loggato"
