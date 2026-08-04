import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import evolution_cloud as evolution
from scripts import evolve_portfolio
from scripts import portfolio_paper
from scripts import research_pack


NOW = datetime(2026, 7, 22, 7, 0, tzinfo=timezone.utc)


def _pack():
    census = [{"symbol": "BTC"}]
    return research_pack._with_pack_id({
        "kind": research_pack.PACK_KIND,
        "generated_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=24)).isoformat(),
        "universe": {
            "census": census,
            "census_sha256": research_pack.content_hash(census),
        },
    })


def _research_maker(pack):
    families = [{
        "family_id": f"portfolio-family-{index}",
        "title": f"Portfolio family {index}",
        "hypothesis": "A falsifiable portfolio hypothesis",
        "mechanism": "A distinct structural return mechanism",
        "data_requirements": ["point-in-time hourly OHLCV"],
        "source_urls": [f"https://example.org/primary/{index}"],
        "novelty_status": "material_variant",
        "data_feasibility": "feasible",
        "blockers": [],
    } for index in range(1, 6)]
    return {
        "kind": research_pack.MAKER_KIND,
        "pack_id": pack["pack_id"],
        "created_at": (NOW + timedelta(minutes=10)).isoformat(),
        "maker_run_id": "research-maker-1",
        "model": "zai:glm-5.1",
        "outcome": "CANDIDATE",
        "inventory": {
            "note_path": "brain plus strategies",
            "checked_at": (NOW + timedelta(minutes=5)).isoformat(),
            "consumed_strategy_ids": ["xsmom-parent-v1"],
            "novelty_summary": "Compared against the active portfolio registry",
        },
        "research_families": families,
        "candidate": {
            "family_id": "portfolio-family-1",
            "thesis": "A faster rebalance may adapt sooner while preserving momentum.",
            "prereg_scope": "One fixed xsmom mutation over the declared paper basket.",
            "data_contract": ["point-in-time hourly OHLCV already supported by AlphaZero"],
            "falsification": "Reject if frozen tail Sharpe does not beat the parent.",
            "next_gate": "PREREG_REVIEW_ONLY",
        },
        "guardrails": dict(research_pack.GUARDRAILS),
    }


def _research_checker(pack, maker):
    return {
        "kind": research_pack.CHECKER_KIND,
        "pack_id": pack["pack_id"],
        "maker_sha256": research_pack.content_hash(maker),
        "maker_run_id": maker["maker_run_id"],
        "checked_at": (NOW + timedelta(minutes=20)).isoformat(),
        "checker_run_id": "research-checker-2",
        "verdict": "APPROVE_PREREG_ONLY",
        "blockers": [],
        "notes": "Independent preregistration review passed.",
        "checks": {key: True for key in research_pack.CHECKS},
    }


def _write_research_bundle(root: Path):
    pack = _pack()
    maker = _research_maker(pack)
    checker = _research_checker(pack, maker)
    (root / "research").mkdir(parents=True)
    (root / "research/pack.json").write_text(json.dumps(pack))
    (root / "research/maker.json").write_text(json.dumps(maker))
    (root / "checker.json").write_text(json.dumps(checker))
    return pack


def _parent():
    return {
        "id": "xsmom-parent-v1",
        "parent": None,
        "status": "champion",
        "engine": "portfolio",
        "created": "2026-07-01",
        "thesis": "Cross-sectional momentum on a liquid perp basket.",
        "universe": {"selection": "all_perps"},
        "paper_symbols": "BTC,ETH,SOL",
        "portfolio": {
            "factor": "xsmom",
            "lookback_h": 168,
            "rebalance_h": 168,
            "long_q": 0.66,
            "short_q": 0.33,
            "gross": 1.0,
            "dollar_neutral": True,
        },
        "timeframe": "1h",
        "decision_every_h": 4,
        "signals": [],
        "exit": {"stop_pct": 0, "target_r": 0, "time_stop_h": 0},
        "risk": {
            "max_leverage": 2,
            "risk_per_trade_pct": 1.0,
            "max_concurrent_positions": 3,
        },
        "evolution": {"mutable": ["portfolio"], "notes": "test parent"},
        "backtest": {},
    }


def _proposal(parent_id="xsmom-parent-v1"):
    return {
        "outcome": "CANDIDATE",
        "blockers": [],
        "parent_id": parent_id,
        "thesis": (
            "The preregistered faster rebalance may preserve xsmom while adapting sooner; "
            "falsified when its frozen tail fails to beat the parent."
        ),
        "portfolio": {
            "factor": "xsmom",
            "lookback_h": 168,
            "rebalance_h": 48,
            "long_q": 0.66,
            "short_q": 0.33,
            "gross": 1.0,
            "dollar_neutral": True,
        },
    }


PASS_REPORT = {
    "kind": "development-tail-oos-proxy-not-official-holdout",
    "months": 6,
    "n_trials": 2,
    "parent": {
        "id": "xsmom-parent-v1",
        "full": {"total_return": 0.1, "sharpe": 1.0, "max_drawdown": -0.1, "rebalances": 20},
        "oos": {"observations": 800, "sharpe": 1.0, "total_return": 0.03, "max_drawdown": -0.1},
    },
    "candidate": {
        "id": "placeholder",
        "full": {"total_return": 0.2, "sharpe": 1.5, "max_drawdown": -0.1, "rebalances": 30},
        "oos": {"observations": 800, "sharpe": 1.2, "total_return": 0.05, "max_drawdown": -0.1},
    },
    "dsr": {"dsr": 0.99, "sr_ann": 1.5, "sr0_ann": 0.2, "n_trials": 2},
    "gates": {
        "enough_oos_observations": True,
        "positive_full_sharpe": True,
        "dsr_at_least_095": True,
        "positive_oos_return": True,
        "oos_drawdown_within_30pct": True,
        "oos_sharpe_beats_parent": True,
        "enough_rebalances": True,
    },
    "gate_pass": True,
}


def _patch_pipeline(monkeypatch):
    parent = _parent()
    monkeypatch.setattr(evolution, "all_specs", lambda: [(Path("parent.yaml"), parent)])
    index = pd.date_range("2026-01-01", periods=evolution.MIN_PANEL_ROWS, freq="h", tz="UTC")
    prices = pd.DataFrame({
        "BTC": np.linspace(100, 200, len(index)),
        "ETH": np.linspace(200, 350, len(index)),
        "SOL": np.linspace(50, 180, len(index)),
    }, index=index)
    monkeypatch.setattr(evolution, "panel", lambda *_args: prices)

    def report(_parent, candidate, _prices, _n_trials):
        value = deepcopy(PASS_REPORT)
        value["candidate"]["id"] = candidate["id"]
        return value

    monkeypatch.setattr(evolution, "_evaluate_pair", report)
    return parent


def _write_json(path: Path, value: dict):
    path.write_text(json.dumps(value))
    return path


def _write_review(path: Path, maker_run_id: str, verdict="APPROVE"):
    blockers = [] if verdict == "APPROVE" else ["semantic mechanism mismatch"]
    return _write_json(path, {
        "maker_run_id": maker_run_id,
        "reviewer": evolution.OPENROUTER_CONTROL_PLANE,
        "verdict": verdict,
        "blockers": blockers,
        "notes": "The mapping preserves the preregistered mechanism.",
        "checks": {key: verdict == "APPROVE" for key in evolution.SEMANTIC_CHECKS},
    })


def _write_provider(path: Path, role: str):
    return _write_json(path, {
        "role": role,
        "model": evolution.OPENROUTER_CONTROL_PLANE,
        "created_at": NOW.isoformat(),
        "usage": {"total_tokens": 10},
        "search_result_count": 0,
    })


def test_end_to_end_codex_bundle_approves_and_publishes_create_once(tmp_path, monkeypatch):
    parent = _patch_pipeline(monkeypatch)
    source = tmp_path / "research-receipt"
    _write_research_bundle(source)
    proposal = _write_json(tmp_path / "proposal.json", _proposal())
    proposal_metadata = _write_provider(tmp_path / "proposal-metadata.json", "evolution-maker")

    maker_out = tmp_path / "evolution-maker"
    assert evolution.run_maker(
        source, maker_out, proposal, proposal_metadata,
    )["outcome"] == "CANDIDATE"
    candidate = yaml.safe_load((maker_out / "candidate.yaml").read_text())
    assert candidate["universe"] == {"selection": "explicit"}
    assert candidate["evolution"]["paper_universe"]["symbols"] == ["BTC", "ETH", "SOL"]

    maker = json.loads((maker_out / "maker.json").read_text())
    review = _write_review(tmp_path / "review.json", maker["maker_run_id"])
    review_metadata = _write_provider(tmp_path / "review-metadata.json", "evolution-checker")
    checker_out = tmp_path / "evolution-checker"
    assert evolution.run_checker(
        maker_out, checker_out, review, review_metadata,
    )["verdict"] == evolution.APPROVE_VERDICT

    repo = tmp_path / "repo"
    (repo / "strategies/generated").mkdir(parents=True)
    (repo / "strategies/generated/xsmom-parent-v1.yaml").write_text(
        yaml.safe_dump(parent, sort_keys=False)
    )
    result = evolution.publish(checker_out, repo)
    assert len(result["changed_paths"]) == 12
    assert evolution.publish(checker_out, repo)["changed_paths"] == []
    assert evolution.validate_published(repo) == [result["strategy_id"]]
    assert evolution.validate_published(
        repo, result["strategy_id"], require_current_admission=True,
    ) == [result["strategy_id"]]

    strategy_path = repo / "strategies/generated" / f"{result['strategy_id']}.yaml"
    strategy = yaml.safe_load(strategy_path.read_text())
    strategy["status"] = "retired"
    strategy_path.write_text(yaml.safe_dump(strategy, sort_keys=False, allow_unicode=True))
    assert evolution.validate_published(repo) == [result["strategy_id"]]
    with pytest.raises(ValueError, match="lifecycle pubblicato invalido"):
        evolution.validate_published(
            repo, result["strategy_id"], require_current_admission=True,
        )


@pytest.mark.parametrize("mutation", [
    {"vol_target": {"enabled": True, "target_vol_ann": 0.2, "vol_window_h": 720,
                    "gross_floor": 0.3, "gross_cap": 1000}},
    {"vol_target": {"enabled": True, "target_vol_ann": 0.2, "vol_window_h": 720,
                    "gross_floor": 0.3, "gross_cap": 1.5, "escape": 1}},
    {"leverage_boost": 10},
    {"gross": float("inf")},
    {"dollar_neutral": 1},
])
def test_strict_registry_rejects_malicious_nested_or_nonfinite_values(mutation):
    proposal = _proposal()
    proposal["portfolio"].update(mutation)
    with pytest.raises(ValueError):
        evolution._validate_proposal(proposal, {_parent()["id"]: _parent()})


def test_effective_vol_target_gross_cannot_exceed_parent_risk():
    proposal = _proposal()
    proposal["portfolio"]["gross"] = 1.5
    proposal["portfolio"]["vol_target"] = {
        "enabled": True,
        "target_vol_ann": 0.2,
        "vol_window_h": 720,
        "gross_floor": 0.3,
        "gross_cap": 1.5,
    }
    with pytest.raises(ValueError, match="gross effettivo"):
        evolution._validate_proposal(proposal, {_parent()["id"]: _parent()})


def test_openrouter_deepseek_v4_pro_is_fixed_for_separate_maker_checker(
    tmp_path, monkeypatch,
):
    _patch_pipeline(monkeypatch)
    source = tmp_path / "research"
    _write_research_bundle(source)
    responses = iter([
        _proposal(),
        {
            "verdict": "APPROVE",
            "blockers": [],
            "notes": "Independent semantic mapping passed.",
            "checks": {key: True for key in evolution.SEMANTIC_CHECKS},
        },
    ])
    calls = []

    def chat(*_args, **kwargs):
        calls.append(kwargs)
        return next(responses), [], {"total_tokens": 25}, "deepseek/deepseek-v4-pro"

    monkeypatch.setattr(evolution.research_cloud, "_openrouter_chat", chat)
    maker_out = tmp_path / "maker"
    evolution.run_openrouter_maker(source, maker_out)
    maker = json.loads((maker_out / "maker.json").read_text())
    assert maker["control_plane"] == evolution.OPENROUTER_CONTROL_PLANE

    checker_out = tmp_path / "checker"
    evolution.run_openrouter_checker(maker_out, checker_out)
    checker = json.loads((checker_out / "evolution-checker.json").read_text())
    assert checker["control_plane"] == evolution.OPENROUTER_CONTROL_PLANE
    assert checker["maker_run_id"] != checker["checker_run_id"]
    assert len(calls) == 2 and all(call["enable_web"] is False for call in calls)


def test_openrouter_maker_prompt_states_literal_falsification_clause(tmp_path, monkeypatch):
    _patch_pipeline(monkeypatch)
    source = tmp_path / "research"
    _write_research_bundle(source)

    def chat(prompt, **_kwargs):
        assert "Falsificata se:" in prompt
        return _proposal(), [], {"total_tokens": 10}, "deepseek/deepseek-v4-pro"

    monkeypatch.setattr(evolution.research_cloud, "_openrouter_chat", chat)
    proposal = evolution.generate_openrouter_proposal(source, tmp_path / "proposal")
    assert proposal["outcome"] == "CANDIDATE"


def test_panel_requires_full_declared_universe_six_months_and_hourly_cadence(tmp_path, monkeypatch):
    parent = _parent()
    candidate = evolution._materialize(_proposal(), parent, _pack())
    index = pd.date_range("2026-01-01", periods=evolution.MIN_PANEL_ROWS, freq="h", tz="UTC")
    good = pd.DataFrame(100.0, index=index, columns=["BTC", "ETH", "SOL"])

    monkeypatch.setattr(evolution, "panel", lambda *_args: good.drop(columns=["SOL"]))
    with pytest.raises(RuntimeError, match="esattamente"):
        evolution._freeze_panel(candidate, tmp_path / "partial")
    monkeypatch.setattr(evolution, "panel", lambda *_args: good.iloc[:-1])
    with pytest.raises(RuntimeError, match="sei mesi"):
        evolution._freeze_panel(candidate, tmp_path / "short")
    broken = good.drop(index=good.index[100])
    monkeypatch.setattr(evolution, "panel", lambda *_args: broken)
    with pytest.raises(RuntimeError, match="sei mesi|cadenza"):
        evolution._freeze_panel(candidate, tmp_path / "gap")


def test_combo_replay_matches_runtime_ranking_and_weights(monkeypatch):
    symbols = ["A", "B", "C", "D", "E"]
    index = pd.date_range("2026-01-01", periods=20, freq="h", tz="UTC")
    rng = np.random.default_rng(2)
    hourly = rng.normal(
        0,
        np.array([0.001, 0.003, 0.006, 0.012, 0.03]),
        size=(len(index), len(symbols)),
    ) + np.array([0.01, 0.005, 0.002, -0.001, -0.004])
    prices = pd.DataFrame(
        100 * np.exp(np.cumsum(hourly, axis=0)),
        index=index,
        columns=symbols,
    )
    portfolio = {
        "factors": ["xsmom", "highvol"],
        "weights": [0.7, 0.3],
        "lookback_h": 6,
        "vol_lookback_h": 5,
        "rebalance_h": 4,
        "long_q": 0.66,
        "short_q": 0.33,
        "gross": 1.0,
        "dollar_neutral": True,
    }

    def fetch(symbol, lookback_h):
        assert lookback_h == 11
        return {"candles": pd.DataFrame({"ts": index, "close": prices[symbol].to_numpy()})}

    monkeypatch.setattr(portfolio_paper, "fetch_live", fetch)
    replay = evolve_portfolio._signal_panel(portfolio, prices)[0].iloc[-1]
    runtime, _ = portfolio_paper.combo_signal(
        symbols,
        portfolio["factors"],
        portfolio["weights"],
        portfolio["lookback_h"],
        portfolio["vol_lookback_h"],
    )

    pd.testing.assert_series_equal(replay, runtime, check_names=False)
    assert replay.sort_values().index.tolist() == runtime.sort_values().index.tolist()
    replay_weights = evolve_portfolio._weight_fn(portfolio)(replay, portfolio["gross"])
    runtime_weights = portfolio_paper.xs_momentum_weights(
        runtime,
        long_q=portfolio["long_q"],
        short_q=portfolio["short_q"],
        gross=portfolio["gross"],
        dollar_neutral=portfolio["dollar_neutral"],
    )
    pd.testing.assert_series_equal(replay_weights, runtime_weights)


def test_combo_replay_matches_runtime_when_cross_section_has_zero_variance(monkeypatch):
    symbols = ["A", "B", "C"]
    index = pd.date_range("2026-01-01", periods=12, freq="h", tz="UTC")
    prices = pd.DataFrame(100.0, index=index, columns=symbols)
    portfolio = {
        "factors": ["xsmom", "highvol"],
        "weights": [0.7, 0.3],
        "lookback_h": 4,
        "vol_lookback_h": 3,
        "rebalance_h": 4,
    }

    monkeypatch.setattr(
        portfolio_paper,
        "fetch_live",
        lambda symbol, lookback_h: {
            "candles": pd.DataFrame({"ts": index, "close": prices[symbol].to_numpy()})
        },
    )
    replay = evolve_portfolio._signal_panel(portfolio, prices)[0].iloc[-1]
    runtime, _ = portfolio_paper.combo_signal(
        symbols, ["xsmom", "highvol"], [0.7, 0.3], 4, 3,
    )

    pd.testing.assert_series_equal(replay, runtime, check_names=False)
    replay_weights = evolve_portfolio._weight_fn(portfolio)(replay, 1.0)
    runtime_weights = portfolio_paper.xs_momentum_weights(runtime, gross=1.0)
    pd.testing.assert_series_equal(replay_weights, runtime_weights)


def test_pair_tail_is_time_aligned_when_parent_and_candidate_lookbacks_differ(monkeypatch):
    parent = _parent()
    candidate = deepcopy(parent)
    candidate["id"] = "xsmom-parent-g1-test"
    candidate["parent"] = parent["id"]
    candidate["portfolio"] = {**candidate["portfolio"], "lookback_h": 24}
    index = pd.date_range("2026-01-01", periods=evolution.MIN_PANEL_ROWS, freq="h", tz="UTC")
    rng = np.random.default_rng(19)
    prices = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.005, size=(len(index), 3)), axis=0)),
        index=index,
        columns=["BTC", "ETH", "SOL"],
    )
    observed = []
    original_metrics = evolution._return_metrics

    def capture_tail(returns):
        observed.append(returns.index.copy())
        return original_metrics(returns)

    monkeypatch.setattr(evolution, "_return_metrics", capture_tail)
    evolution._evaluate_pair(parent, candidate, prices, n_trials=2)

    expected = index[len(index) * 2 // 3:]
    assert len(observed) == 2
    assert observed[0].equals(expected)
    assert observed[1].equals(expected)


def test_eval_excludes_only_warmup_and_preserves_economic_zero_returns():
    index = pd.date_range("2026-01-01", periods=96, freq="h", tz="UTC")
    prices = pd.DataFrame(100.0, index=index, columns=["BTC", "ETH", "SOL"])
    spec = deepcopy(_parent())
    spec["portfolio"] = {**spec["portfolio"], "lookback_h": 24, "rebalance_h": 24}

    _, returns = evolve_portfolio.eval_portfolio(spec, prices, months=1)

    assert returns.index.equals(index[24:])
    assert (returns == 0.0).all()


def test_checker_rejects_candidate_tampering(tmp_path, monkeypatch):
    _patch_pipeline(monkeypatch)
    source = tmp_path / "research-receipt"
    _write_research_bundle(source)
    proposal = _write_json(tmp_path / "proposal.json", _proposal())
    proposal_metadata = _write_provider(tmp_path / "proposal-metadata.json", "evolution-maker")
    maker_out = tmp_path / "evolution-maker"
    evolution.run_maker(source, maker_out, proposal, proposal_metadata)
    candidate = yaml.safe_load((maker_out / "candidate.yaml").read_text())
    candidate["risk"]["max_leverage"] = 99
    (maker_out / "candidate.yaml").write_text(yaml.safe_dump(candidate))
    maker = json.loads((maker_out / "maker.json").read_text())
    review = _write_review(tmp_path / "review.json", maker["maker_run_id"])
    review_metadata = _write_provider(tmp_path / "review-metadata.json", "evolution-checker")
    with pytest.raises(ValueError, match="file hash mismatch"):
        evolution.run_checker(maker_out, tmp_path / "checker", review, review_metadata)


def test_family_challenger_cap_removes_parent(monkeypatch):
    parent = _parent()
    challengers = []
    for index in range(evolution.MAX_FAMILY_CHALLENGERS):
        item = deepcopy(parent)
        item["id"] = f"xsmom-parent-g{index}"
        item["status"] = "challenger"
        challengers.append((Path(f"g{index}.yaml"), item))
    monkeypatch.setattr(
        evolution,
        "all_specs",
        lambda: [(Path("parent.yaml"), parent), *challengers],
    )
    assert evolution._active_parents() == {}


def test_changed_admission_selector_runs_strict_validation(tmp_path, monkeypatch):
    diff = (
        "README.md\n"
        "evidence/evolution/xsmom-port-g123/maker.json\n"
        "evidence/evolution/xsmom-port-g123/checker.json\n"
    )
    monkeypatch.setattr(
        evolution.subprocess,
        "run",
        lambda *_args, **_kwargs: evolution.subprocess.CompletedProcess(
            args=[], returncode=0, stdout=diff,
        ),
    )
    calls = []

    def validate(repo, strategy_id, *, require_current_admission=False):
        calls.append((Path(repo), strategy_id, require_current_admission))
        return [strategy_id]

    monkeypatch.setattr(evolution, "validate_published", validate)
    assert evolution.validate_changed_admissions(tmp_path, "HEAD^") == ["xsmom-port-g123"]
    assert calls == [(tmp_path, "xsmom-port-g123", True)]


def test_publish_and_validator_enforce_family_challenger_cap(tmp_path, monkeypatch):
    parent = _patch_pipeline(monkeypatch)
    source = tmp_path / "research"
    _write_research_bundle(source)
    proposal = _write_json(tmp_path / "proposal.json", _proposal())
    proposal_metadata = _write_provider(tmp_path / "proposal-metadata.json", "evolution-maker")
    maker_out = tmp_path / "maker"
    evolution.run_maker(source, maker_out, proposal, proposal_metadata)
    maker = json.loads((maker_out / "maker.json").read_text())
    review = _write_review(tmp_path / "review.json", maker["maker_run_id"])
    review_metadata = _write_provider(tmp_path / "review-metadata.json", "evolution-checker")
    checker_out = tmp_path / "checker"
    evolution.run_checker(maker_out, checker_out, review, review_metadata)

    repo = tmp_path / "repo"
    generated = repo / "strategies/generated"
    generated.mkdir(parents=True)
    (generated / "xsmom-parent-v1.yaml").write_text(
        yaml.safe_dump(parent, sort_keys=False)
    )
    challenger_paths = []
    for index in range(evolution.MAX_FAMILY_CHALLENGERS):
        challenger = deepcopy(parent)
        challenger["id"] = f"xsmom-parent-g{1000 + index}"
        challenger["status"] = "challenger"
        path = generated / f"{challenger['id']}.yaml"
        path.write_text(yaml.safe_dump(challenger, sort_keys=False))
        challenger_paths.append(path)

    with pytest.raises(ValueError, match="family challenger cap"):
        evolution.publish(checker_out, repo)

    challenger_paths[-1].unlink()
    result = evolution.publish(checker_out, repo)
    assert evolution.validate_published(repo) == [result["strategy_id"]]

    challenger = deepcopy(parent)
    challenger["id"] = "xsmom-parent-g9999"
    challenger["status"] = "challenger"
    challenger_paths[-1].write_text(yaml.safe_dump(challenger, sort_keys=False))
    assert evolution.validate_published(repo) == [result["strategy_id"]]
    with pytest.raises(ValueError, match="family challenger cap"):
        evolution.validate_published(
            repo, result["strategy_id"], require_current_admission=True,
        )


def test_historical_validation_allows_parent_drift_but_admission_rejects_it(
    tmp_path, monkeypatch,
):
    parent = _patch_pipeline(monkeypatch)
    source = tmp_path / "research"
    _write_research_bundle(source)
    proposal = _write_json(tmp_path / "proposal.json", _proposal())
    proposal_metadata = _write_provider(tmp_path / "proposal-metadata.json", "evolution-maker")
    maker_out = tmp_path / "maker"
    evolution.run_maker(source, maker_out, proposal, proposal_metadata)
    maker = json.loads((maker_out / "maker.json").read_text())
    review = _write_review(tmp_path / "review.json", maker["maker_run_id"])
    review_metadata = _write_provider(tmp_path / "review-metadata.json", "evolution-checker")
    checker_out = tmp_path / "checker"
    evolution.run_checker(maker_out, checker_out, review, review_metadata)
    repo = tmp_path / "repo"
    (repo / "strategies/generated").mkdir(parents=True)
    parent_path = repo / "strategies/generated/xsmom-parent-v1.yaml"
    parent_path.write_text(yaml.safe_dump(parent, sort_keys=False))
    result = evolution.publish(checker_out, repo)
    changed_parent = deepcopy(parent)
    changed_parent["risk"]["max_leverage"] = 1.5
    parent_path.write_text(yaml.safe_dump(changed_parent, sort_keys=False))
    assert evolution.validate_published(repo) == [result["strategy_id"]]
    with pytest.raises(ValueError, match="parent stale"):
        evolution.validate_published(
            repo, result["strategy_id"], require_current_admission=True,
        )


def test_publish_rejects_parent_that_changed_after_maker(tmp_path, monkeypatch):
    parent = _patch_pipeline(monkeypatch)
    source = tmp_path / "research"
    _write_research_bundle(source)
    proposal = _write_json(tmp_path / "proposal.json", _proposal())
    proposal_metadata = _write_provider(tmp_path / "proposal-metadata.json", "evolution-maker")
    maker_out = tmp_path / "maker"
    evolution.run_maker(source, maker_out, proposal, proposal_metadata)
    maker = json.loads((maker_out / "maker.json").read_text())
    review = _write_review(tmp_path / "review.json", maker["maker_run_id"])
    review_metadata = _write_provider(tmp_path / "review-metadata.json", "evolution-checker")
    checker_out = tmp_path / "checker"
    evolution.run_checker(maker_out, checker_out, review, review_metadata)

    repo = tmp_path / "repo"
    (repo / "strategies/generated").mkdir(parents=True)
    parent["status"] = "retired"
    (repo / "strategies/generated/xsmom-parent-v1.yaml").write_text(
        yaml.safe_dump(parent, sort_keys=False)
    )
    with pytest.raises(ValueError, match="non piu attivo"):
        evolution.publish(checker_out, repo)


def test_runtime_rejects_internal_evolution_universe_drift():
    symbols = ["BTC", "ETH", "SOL"]
    spec = {
        "evolution": {
            "paper_universe": {
                "schema_version": 1,
                "source_parent_selection": "all_perps",
                "symbols": symbols,
                "symbols_sha256": evolution.content_hash(symbols),
            }
        }
    }
    assert portfolio_paper._validated_evolution_symbols(spec, symbols) == symbols
    with pytest.raises(SystemExit, match="diverge"):
        portfolio_paper._validated_evolution_symbols(spec, ["BTC", "ETH", "XRP"])


def test_l2_actions_is_read_only_intake_and_never_calls_provider_or_pushes():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/evolution-intake.yml").read_text()
    assert "workflow_run:" in workflow and "workflows: [research-checker]" in workflow
    assert "permissions:\n  actions: read\n  contents: read" in workflow
    assert '".github/workflows/evolution-intake.yml"' in workflow
    assert '"$(jq -r \'.conclusion\' <<< "$disposition_run")" = "success"' in workflow
    for forbidden in ("ZAI_API_KEY", "OPENROUTER_API_KEY", "git push", "gh pr create", "git merge"):
        assert forbidden not in workflow
