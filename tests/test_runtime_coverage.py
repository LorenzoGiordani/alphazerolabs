import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_portfolio_partial_universe_blocks_without_state_write(tmp_path, monkeypatch):
    import scripts.portfolio_paper as portfolio

    state = tmp_path / "state.json"
    spec = {"id": "alpha-port-v1", "engine": "portfolio", "status": "challenger",
            "portfolio": {"lookback_h": 24, "rebalance_h": 24, "factor": "xsmom"}}
    monkeypatch.setattr(portfolio, "STATE_FILE", state)
    monkeypatch.setattr(portfolio, "load", lambda _path: spec)
    monkeypatch.setattr(portfolio, "paper_symbols", lambda _spec: "A,B,C")
    monkeypatch.setattr(portfolio, "trailing_returns",
                        lambda *_args: (pd.Series({"A": 0.1, "B": -0.1}), {"A": 10.0, "B": 20.0}))
    monkeypatch.setattr(portfolio, "perp_market_snapshot", lambda: [])
    monkeypatch.setattr(sys, "argv", ["portfolio_paper.py", "alpha.yaml"])
    with pytest.raises(SystemExit, match="copertura prezzi incompleta"):
        portfolio.main()
    assert not state.exists()


def test_liqimb_cannot_claim_three_of_nine_as_complete(tmp_path, monkeypatch):
    import scripts.portfolio_paper as portfolio

    state = tmp_path / "state.json"
    symbols = "BTC,ETH,SOL,XRP,SUI,NEAR,WLD,ZEC,CRV"
    spec = {"id": "liqimb-port-v1", "engine": "portfolio", "status": "champion",
            "portfolio": {"lookback_h": 24, "rebalance_h": 24, "factor": "liqimb",
                          "liq_lookback_d": 7}}
    monkeypatch.setattr(portfolio, "STATE_FILE", state)
    monkeypatch.setattr(portfolio, "load", lambda _path: spec)
    monkeypatch.setattr(portfolio, "paper_symbols", lambda _spec: symbols)
    all_prices = {symbol: float(index + 1) for index, symbol in enumerate(symbols.split(","))}
    monkeypatch.setattr(portfolio, "liqimb_signal", lambda *_args: (
        pd.Series({"BTC": 0.1, "ETH": 0.0, "SOL": -0.1}), all_prices))
    monkeypatch.setattr(sys, "argv", ["portfolio_paper.py", "liqimb.yaml"])
    with pytest.raises(SystemExit, match="3/9"):
        portfolio.main()
    record = json.loads((tmp_path / "coverage/liqimb-port-v1-signal-eligible.json").read_text())
    assert record["expected_count"] == 9
    assert record["observed_count"] == 3
    assert len(record["missing"]) == 6
    assert record["critical"] is True


def test_new_listing_price_is_covered_but_signal_waits_for_history(tmp_path, monkeypatch):
    import scripts.portfolio_paper as portfolio

    state = tmp_path / "state.json"
    spec = {"id": "alpha-port-v1", "engine": "portfolio", "status": "challenger",
            "portfolio": {"lookback_h": 24, "rebalance_h": 24, "factor": "xsmom"}}
    monkeypatch.setattr(portfolio, "STATE_FILE", state)
    monkeypatch.setattr(portfolio, "load", lambda _path: spec)
    monkeypatch.setattr(portfolio, "paper_symbols", lambda _spec: "A,B,C,D,NEW")
    monkeypatch.setattr(portfolio, "trailing_returns", lambda *_args: (
        pd.Series({"A": 0.2, "B": 0.1, "C": -0.1, "D": -0.2}),
        {"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0, "NEW": 5.0}))
    monkeypatch.setattr(portfolio, "log_event", lambda _event: None)
    monkeypatch.setattr(sys, "argv", ["portfolio_paper.py", "alpha.yaml"])

    portfolio.main()

    prices = json.loads((tmp_path / "coverage/alpha-port-v1-prices.json").read_text())
    signals = json.loads((tmp_path / "coverage/alpha-port-v1-signal-eligible.json").read_text())
    assert prices["status"] == "pass" and prices["observed_count"] == 5
    assert signals["critical"] is False and signals["missing"] == ["NEW"]
    assert state.exists()


def test_held_asset_uses_market_mark_without_inventing_signal(tmp_path, monkeypatch):
    import scripts.portfolio_paper as portfolio

    state = tmp_path / "state.json"
    spec = {"id": "alpha-port-v1", "engine": "portfolio", "status": "challenger",
            "portfolio": {"lookback_h": 24, "rebalance_h": 24, "factor": "xsmom"}}
    monkeypatch.setattr(portfolio, "STATE_FILE", state)
    monkeypatch.setattr(portfolio, "load", lambda _path: spec)
    monkeypatch.setattr(portfolio, "paper_symbols", lambda _spec: "A,B,C,D,E")
    monkeypatch.setattr(portfolio, "trailing_returns", lambda *_args: (
        pd.Series({"A": 0.2, "B": 0.1, "C": -0.1, "D": -0.2}),
        {"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0}))
    monkeypatch.setattr(portfolio, "perp_market_snapshot", lambda: [
        {"symbol": "E", "mark": 50.0}])
    monkeypatch.setattr(portfolio, "log_event", lambda _event: None)
    monkeypatch.setattr(sys, "argv", ["portfolio_paper.py", "alpha.yaml"])
    last_rebalance = pd.Timestamp.now(tz="UTC").isoformat()
    state.write_text(json.dumps({"alpha-port-v1": {
        "equity": 10_000.0,
        "positions": {"E": {"notional": 100.0, "px": 40.0}},
        "last_rebalance_ts": last_rebalance,
        "equity_history": [],
    }}))

    portfolio.main()

    prices = json.loads((tmp_path / "coverage/alpha-port-v1-prices.json").read_text())
    signals = json.loads((tmp_path / "coverage/alpha-port-v1-signal-eligible.json").read_text())
    updated = json.loads(state.read_text())["alpha-port-v1"]
    assert prices["status"] == "pass" and prices["observed_count"] == 5
    assert signals["missing"] == ["E"]
    assert updated["last_rebalance_ts"] == last_rebalance
    assert updated["positions"]["E"] == {"notional": 125.0, "px": 50.0}


def test_due_rebalance_with_held_mark_only_asset_leaves_state_unchanged(tmp_path, monkeypatch):
    import scripts.portfolio_paper as portfolio

    state = tmp_path / "state.json"
    spec = {"id": "alpha-port-v1", "engine": "portfolio", "status": "challenger",
            "portfolio": {"lookback_h": 24, "rebalance_h": 24, "factor": "xsmom"}}
    initial = json.dumps({"alpha-port-v1": {
        "equity": 10_000.0,
        "positions": {"E": {"notional": 100.0, "px": 40.0}},
        "last_rebalance_ts": "",
        "equity_history": [],
    }})
    state.write_text(initial)
    monkeypatch.setattr(portfolio, "STATE_FILE", state)
    monkeypatch.setattr(portfolio, "load", lambda _path: spec)
    monkeypatch.setattr(portfolio, "paper_symbols", lambda _spec: "A,B,C,D,E")
    monkeypatch.setattr(portfolio, "trailing_returns", lambda *_args: (
        pd.Series({"A": 0.2, "B": 0.1, "C": -0.1, "D": -0.2}),
        {"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0}))
    monkeypatch.setattr(portfolio, "perp_market_snapshot", lambda: [
        {"symbol": "E", "mark": 50.0}])
    monkeypatch.setattr(portfolio, "atomic_write_text", lambda *_args: (
        _ for _ in ()).throw(AssertionError("state write during deferred rebalance")))
    monkeypatch.setattr(portfolio, "log_event", lambda _event: (
        _ for _ in ()).throw(AssertionError("journal write during deferred rebalance")))
    monkeypatch.setattr(sys, "argv", ["portfolio_paper.py", "alpha.yaml"])

    portfolio.main()

    prices = json.loads((tmp_path / "coverage/alpha-port-v1-prices.json").read_text())
    signals = json.loads((tmp_path / "coverage/alpha-port-v1-signal-eligible.json").read_text())
    assert prices["status"] == "pass" and signals["missing"] == ["E"]
    assert state.read_text() == initial


def test_portfolio_child_uses_shared_marks_without_live_snapshot(tmp_path, monkeypatch):
    import scripts.portfolio_paper as portfolio

    snapshot = tmp_path / "marks.json"
    snapshot.write_text(json.dumps({"ok": True, "rows": [
        {"symbol": "A", "mark": 10.0}, {"symbol": "B", "mark": 20.0},
    ]}))
    monkeypatch.setenv(portfolio.MARK_SNAPSHOT_ENV, str(snapshot))
    monkeypatch.setattr(portfolio, "perp_market_snapshot", lambda: (
        _ for _ in ()).throw(AssertionError("live snapshot called")))

    assert portfolio.market_marks() == {"A": 10.0, "B": 20.0}


def test_empty_shared_mark_path_does_not_refetch_live(monkeypatch):
    import scripts.portfolio_paper as portfolio

    monkeypatch.setenv(portfolio.MARK_SNAPSHOT_ENV, "")
    monkeypatch.setattr(portfolio, "perp_market_snapshot", lambda: (
        _ for _ in ()).throw(AssertionError("live snapshot called")))

    with pytest.raises(RuntimeError, match="condivisa illeggibile"):
        portfolio.market_marks()


def test_invalid_shared_marks_fail_closed_before_state_write(tmp_path, monkeypatch):
    import scripts.portfolio_paper as portfolio

    state = tmp_path / "state.json"
    spec = {"id": "alpha-port-v1", "engine": "portfolio", "status": "challenger",
            "portfolio": {"lookback_h": 24, "rebalance_h": 24, "factor": "xsmom"}}
    monkeypatch.setattr(portfolio, "STATE_FILE", state)
    monkeypatch.setattr(portfolio, "load", lambda _path: spec)
    monkeypatch.setattr(portfolio, "paper_symbols", lambda _spec: "A,B,C")
    monkeypatch.setattr(portfolio, "trailing_returns", lambda *_args: (
        pd.Series({"A": 0.1, "B": -0.1}), {"A": 10.0, "B": 20.0}))
    monkeypatch.setenv(portfolio.MARK_SNAPSHOT_ENV, str(tmp_path / "missing.json"))
    monkeypatch.setattr(portfolio, "perp_market_snapshot", lambda: (
        _ for _ in ()).throw(AssertionError("live snapshot called")))
    monkeypatch.setattr(sys, "argv", ["portfolio_paper.py", "alpha.yaml"])

    with pytest.raises(SystemExit, match="copertura prezzi incompleta"):
        portfolio.main()

    assert not state.exists()


def test_too_narrow_signal_eligible_subset_blocks(tmp_path, monkeypatch):
    import scripts.portfolio_paper as portfolio

    state = tmp_path / "state.json"
    spec = {"id": "alpha-port-v1", "engine": "portfolio", "status": "challenger",
            "portfolio": {"lookback_h": 24, "rebalance_h": 24, "factor": "xsmom"}}
    monkeypatch.setattr(portfolio, "STATE_FILE", state)
    monkeypatch.setattr(portfolio, "load", lambda _path: spec)
    monkeypatch.setattr(portfolio, "paper_symbols", lambda _spec: "A,B,C,D,E")
    monkeypatch.setattr(portfolio, "trailing_returns", lambda *_args: (
        pd.Series({"A": 0.2, "B": 0.0, "C": -0.2}),
        {"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0, "E": 50.0}))
    monkeypatch.setattr(sys, "argv", ["portfolio_paper.py", "alpha.yaml"])

    with pytest.raises(SystemExit, match="segnali eleggibili insufficienti: 3/5"):
        portfolio.main()
    assert not state.exists()


def test_liqimb_stale_source_is_not_signal_eligible(tmp_path, monkeypatch):
    import scripts.portfolio_paper as portfolio

    source = tmp_path / "data/coinalyze_1h"
    source.mkdir(parents=True)
    end = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=9)
    ts = pd.date_range(end=end, periods=168, freq="h")
    pd.DataFrame({"ts": ts, "liq_long": 1.0, "liq_short": 2.0,
                  "oi": 100.0}).to_parquet(source / "BTC.parquet", index=False)
    monkeypatch.setattr(portfolio, "ROOT", tmp_path)
    monkeypatch.setattr(portfolio, "fetch_live", lambda *_args, **_kwargs: {
        "candles": pd.DataFrame({"close": [10.0]})})

    signal, prices = portfolio.liqimb_signal(["BTC"], 7)

    assert prices == {"BTC": 10.0}
    assert signal.empty


def test_multihorizon_requires_every_declared_lookback(monkeypatch):
    import scripts.portfolio_paper as portfolio

    candles = pd.DataFrame({"close": [float(i + 1) for i in range(200)]})
    monkeypatch.setattr(portfolio, "fetch_live", lambda *_args, **_kwargs: {
        "candles": candles})

    signal, prices = portfolio.trailing_returns(["NEW"], 96, [96, 168, 336])

    assert prices == {"NEW": 200.0}
    assert signal.empty


def test_paper_trade_prefetches_every_ticker_before_mutating(tmp_path, monkeypatch):
    import scripts.paper_trade as paper

    state = tmp_path / "state.json"
    spec = {"id": "alpha-v1", "signals": [],
            "risk": {"max_concurrent_positions": 1}}
    monkeypatch.setattr(paper, "STATE_FILE", state)
    monkeypatch.setattr(paper, "load", lambda _path: spec)
    monkeypatch.setattr(paper, "log_event",
                        lambda _event: (_ for _ in ()).throw(AssertionError("mutation before coverage gate")))

    def fetch(symbol):
        if symbol == "B":
            raise RuntimeError("feed down")
        return {"candles": pd.DataFrame(), "forming": None}

    monkeypatch.setattr(paper, "fetch_live_cached", fetch)
    monkeypatch.setattr(sys, "argv", ["paper_trade.py", "alpha.yaml", "A,B"])
    with pytest.raises(SystemExit, match="copertura ticker incompleta"):
        paper.main()
    assert not state.exists()


def test_required_signal_source_missing_blocks_before_mutation(tmp_path, monkeypatch):
    import scripts.paper_trade as paper

    state = tmp_path / "state.json"
    spec = {"id": "alpha-v1", "signals": [{"name": "taker_flow"}],
            "risk": {"max_concurrent_positions": 1}}
    monkeypatch.setattr(paper, "STATE_FILE", state)
    monkeypatch.setattr(paper, "load", lambda _path: spec)
    monkeypatch.setattr(paper, "fetch_live_cached", lambda _symbol: {
        "candles": pd.DataFrame(), "forming": None, "funding": None, "flow": None})
    monkeypatch.setattr(paper, "log_event",
                        lambda _event: (_ for _ in ()).throw(
                            AssertionError("mutation before source coverage gate")))
    monkeypatch.setattr(sys, "argv", ["paper_trade.py", "alpha.yaml", "A,B,C"])

    with pytest.raises(SystemExit, match="taker_flow=0/3"):
        paper.main()

    record = json.loads((tmp_path / "coverage/alpha-v1-source-taker-flow.json").read_text())
    assert record["critical"] is True and record["missing"] == ["A", "B", "C"]
    assert not state.exists()


def test_runner_propagates_child_failures(tmp_path, monkeypatch):
    import scripts.paper_all as runner

    specs = [(Path("a.yaml"), {"id": "a-v1", "status": "challenger", "risk": {}}),
             (Path("b.yaml"), {"id": "b-v1", "status": "challenger", "risk": {}})]
    outcomes = iter([SimpleNamespace(returncode=0), SimpleNamespace(returncode=3)])
    monkeypatch.setattr(runner, "active_specs", lambda: specs)
    monkeypatch.setattr(runner, "paper_symbols", lambda _spec: "BTC")
    monkeypatch.setattr(runner, "validate_spec_risk", lambda _spec: [])
    monkeypatch.setattr(runner, "COVERAGE_DIR", tmp_path)
    monkeypatch.setattr(runner.subprocess, "run", lambda *_args, **_kwargs: next(outcomes))
    with pytest.raises(SystemExit, match="b-v1"):
        runner.main()


def test_portfolio_runner_fetches_one_shared_snapshot(tmp_path, monkeypatch):
    import scripts.portfolio_all as runner

    specs = [(Path("a.yaml"), {"id": "a-v1", "status": "challenger"}),
             (Path("b.yaml"), {"id": "b-v1", "status": "champion"})]
    calls = []
    snapshot_calls = []
    monkeypatch.setattr(runner, "portfolio_active_specs", lambda: specs)
    monkeypatch.setattr(runner, "COVERAGE_DIR", tmp_path)

    def snapshot():
        snapshot_calls.append(True)
        return [{"symbol": "BTC", "mark": 100.0}]

    monkeypatch.setattr(runner, "perp_market_snapshot", snapshot)

    def run(_command, *, env):
        calls.append((env[runner.MARK_SNAPSHOT_ENV], json.loads(
            Path(env[runner.MARK_SNAPSHOT_ENV]).read_text())))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", run)

    runner.main()

    assert len(snapshot_calls) == 1
    assert len(calls) == 2
    assert calls[0][0] == calls[1][0]
    assert calls[0][1] == {"ok": True, "rows": [{"symbol": "BTC", "mark": 100.0}]}


def test_portfolio_runner_shares_one_failure_without_child_refetch(tmp_path, monkeypatch):
    import scripts.portfolio_all as runner

    specs = [(Path("a.yaml"), {"id": "a-v1", "status": "challenger"}),
             (Path("b.yaml"), {"id": "b-v1", "status": "champion"})]
    payloads = []
    snapshot_calls = []
    monkeypatch.setattr(runner, "portfolio_active_specs", lambda: specs)
    monkeypatch.setattr(runner, "COVERAGE_DIR", tmp_path)

    def snapshot():
        snapshot_calls.append(True)
        raise RuntimeError("HL HTTP 429")

    def run(_command, *, env):
        payloads.append(json.loads(Path(env[runner.MARK_SNAPSHOT_ENV]).read_text()))
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(runner, "perp_market_snapshot", snapshot)
    monkeypatch.setattr(runner.subprocess, "run", run)

    with pytest.raises(SystemExit, match="a-v1, b-v1"):
        runner.main()

    assert len(snapshot_calls) == 1
    assert payloads == [{"ok": False, "error": "HL HTTP 429"}] * 2
