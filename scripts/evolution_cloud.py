"""Research OS L2: approved preregistration to a paper-only strategy PR.

GitHub Actions creates a read-only intake.  A DeepSeek V4 Pro Maker supplies one
proposal through OpenRouter and a separate call supplies one independent review.
This module validates those immutable inputs, freezes and replays the panel, and
materialises a human-PR bundle.  It never pushes, merges, trades live, or deploys
capital.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from backtest.evidence import strategy_logic_sha256
from backtest.lifecycle import all_specs, family
from backtest.stats import deflated_sharpe
from scripts import research_cloud, research_pack
from scripts.evolve_portfolio import (
    EVOLVABLE_FACTORS,
    MAX_FAMILY_CHALLENGERS,
    eval_portfolio,
    panel,
    validate_portfolio,
)


ROOT = Path(__file__).resolve().parent.parent
MAKER_KIND = "strategy-evolution-maker.v1"
CHECKER_KIND = "strategy-evolution-checker.v1"
APPROVE_VERDICT = "APPROVE_CHALLENGER_PR"
OPENROUTER_CONTROL_PLANE = f"openrouter:{research_cloud.OPENROUTER_MODEL}"
MONTHS = 6
MIN_PANEL_ROWS = MONTHS * 30 * 24
MIN_OOS_OBS = 720
MIN_REBALANCES = 12
MIN_DSR = 0.95
MAX_OOS_DRAWDOWN = -0.30
MIN_OOS_SHARPE_EDGE = 0.10
PPY = 24 * 365
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
GUARDRAILS = {
    "paper_only": True,
    "closed_registry_only": True,
    "immutable_risk": True,
    "no_arbitrary_code": True,
    "no_auto_merge": True,
    "no_live_orders": True,
    "no_capital": True,
}
SEMANTIC_CHECKS = {
    "prereg_alignment",
    "mechanism_preserved",
    "data_contract_supported",
    "no_hindsight_or_new_code",
}
PORTFOLIO_KEYS = {
    "factor", "factors", "weights", "lookback_h", "lookbacks_h",
    "vol_lookback_h", "rebalance_h", "long_q", "short_q", "gross",
    "dollar_neutral", "vol_target",
}
VOL_TARGET_KEYS = {
    "enabled", "target_vol_ann", "vol_window_h", "gross_floor", "gross_cap",
}
HISTORICAL_LIFECYCLE_STATUSES = {"challenger", "champion", "retired"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False, default=str,
    )


def content_hash(value) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: atteso oggetto JSON")
    return value


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _yaml_bytes(value: dict) -> bytes:
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True).encode()


def _write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_yaml_bytes(value))


def _parse_ts(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp senza timezone")
    return parsed.astimezone(timezone.utc)


def _repo_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True,
    )
    return result.stdout.strip()


def _expect_keys(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        got = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ValueError(f"{label}: chiavi attese {sorted(keys)}, ricevute {got}")
    return value


def _research_paths(root: Path) -> tuple[Path, Path, Path]:
    research = root / "research"
    return research / "pack.json", research / "maker.json", root / "checker.json"


def _load_approved_research(root: Path) -> tuple[dict, dict, dict]:
    pack_path, maker_path, checker_path = _research_paths(root)
    pack, maker, checker = map(_read_json, (pack_path, maker_path, checker_path))
    checked_at = _parse_ts(checker.get("checked_at"))
    result = research_pack.validate_checker(pack, maker, checker, now=checked_at)
    if result["verdict"] != "APPROVE_PREREG_ONLY" or maker.get("candidate") is None:
        raise ValueError("L2 richiede una receipt APPROVE_PREREG_ONLY con candidata")
    return pack, maker, checker


def _portfolio_factors(spec: dict) -> set[str]:
    portfolio = spec.get("portfolio") or {}
    return set(portfolio.get("factors") or [portfolio.get("factor", "xsmom")])


def _active_parents() -> dict[str, dict]:
    specs = [spec for _, spec in all_specs()]
    active_challengers: dict[str, int] = {}
    for spec in specs:
        if spec.get("engine") == "portfolio" and spec.get("status") == "challenger":
            fam = family(spec["id"])
            active_challengers[fam] = active_challengers.get(fam, 0) + 1
    parents = {}
    for spec in specs:
        if spec.get("engine") != "portfolio":
            continue
        if spec.get("status") not in ("champion", "challenger"):
            continue
        if not _portfolio_factors(spec) <= set(EVOLVABLE_FACTORS):
            continue
        if active_challengers.get(family(spec["id"]), 0) >= MAX_FAMILY_CHALLENGERS:
            continue
        symbols = spec.get("paper_symbols")
        if not symbols:
            continue
        parents[spec["id"]] = spec
    return dict(sorted(parents.items()))


def _parent_inventory(parents: dict[str, dict]) -> list[dict]:
    return [
        {
            "id": sid,
            "status": spec["status"],
            "thesis": spec.get("thesis", ""),
            "paper_symbols": spec.get("paper_symbols"),
            "portfolio": spec.get("portfolio"),
            "risk": spec.get("risk"),
            "recent_backtest": spec.get("backtest", {}),
        }
        for sid, spec in parents.items()
    ]


def _validate_proposal(value: dict, parents: dict[str, dict]) -> dict:
    value = _expect_keys(
        value,
        {"outcome", "blockers", "parent_id", "thesis", "portfolio"},
        "evolution proposal",
    )
    if value["outcome"] not in ("BLOCKED", "CANDIDATE"):
        raise ValueError("proposal.outcome invalido")
    if not isinstance(value["blockers"], list) or any(
        not isinstance(item, str) or not item.strip() for item in value["blockers"]
    ):
        raise ValueError("proposal.blockers deve essere una lista di stringhe")
    if value["outcome"] == "BLOCKED":
        if not value["blockers"] or any(
            value[field] is not None for field in ("parent_id", "thesis", "portfolio")
        ):
            raise ValueError("BLOCKED richiede blocker e nessuna mutazione")
        return value
    if value["blockers"]:
        raise ValueError("CANDIDATE non puo avere blocker")
    if value["parent_id"] not in parents:
        raise ValueError("parent_id non e attivo o non e evolvibile")
    if not isinstance(value["thesis"], str) or len(value["thesis"].strip()) < 40:
        raise ValueError("thesis troppo corta")
    if "falsif" not in value["thesis"].lower():
        raise ValueError("thesis deve includere una clausola di falsificazione")
    if not isinstance(value["portfolio"], dict):
        raise ValueError("portfolio mancante")
    _validate_l2_portfolio(value["portfolio"], parents[value["parent_id"]])
    return value


def _finite_number(value: object, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} deve essere numerico")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{label} fuori range [{low},{high}]")
    return number


def _strict_int(value: object, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{label} deve essere intero in [{low},{high}]")
    return value


def _validate_l2_portfolio(portfolio: dict, parent: dict) -> None:
    """Strict L2 boundary around the permissive legacy portfolio validator."""
    if set(portfolio) - PORTFOLIO_KEYS:
        raise ValueError(f"knob portfolio fuori registry: {sorted(set(portfolio) - PORTFOLIO_KEYS)}")
    if not {"rebalance_h", "gross", "dollar_neutral"} <= set(portfolio):
        raise ValueError("rebalance_h, gross e dollar_neutral sono obbligatori")
    _strict_int(portfolio["rebalance_h"], "rebalance_h", 4, 336)
    gross = _finite_number(portfolio["gross"], "gross", 0.3, 1.5)
    if type(portfolio["dollar_neutral"]) is not bool:
        raise ValueError("dollar_neutral deve essere booleano")

    factor = portfolio.get("factor")
    factors = portfolio.get("factors")
    if (factor is None) == (factors is None):
        raise ValueError("specificare esattamente factor oppure factors")
    if factors is not None:
        if factors != ["xsmom", "highvol"]:
            raise ValueError("combo L2 consentita solo come [xsmom, highvol]")
        weights = portfolio.get("weights")
        if not isinstance(weights, list) or len(weights) != 2:
            raise ValueError("weights combo deve contenere due valori")
        clean_weights = [_finite_number(item, "weights", 0.0, 1.0) for item in weights]
        if not math.isclose(sum(clean_weights), 1.0, abs_tol=1e-9):
            raise ValueError("weights combo deve sommare esattamente a 1")
        _strict_int(portfolio.get("lookback_h"), "lookback_h", 24, 720)
        _strict_int(portfolio.get("vol_lookback_h"), "vol_lookback_h", 24, 336)
        if "lookbacks_h" in portfolio:
            raise ValueError("lookbacks_h non ammesso nella combo")
    else:
        if factor not in EVOLVABLE_FACTORS:
            raise ValueError(f"factor fuori registry: {factor}")
        if "weights" in portfolio:
            raise ValueError("weights richiede factors")
        if factor == "highvol":
            _strict_int(portfolio.get("vol_lookback_h"), "vol_lookback_h", 24, 336)
            if "lookback_h" in portfolio or "lookbacks_h" in portfolio:
                raise ValueError("highvol non accetta lookback momentum")
        else:
            has_single = "lookback_h" in portfolio
            has_multi = "lookbacks_h" in portfolio
            if has_single == has_multi:
                raise ValueError("specificare esattamente lookback_h oppure lookbacks_h")
            if has_single:
                _strict_int(portfolio["lookback_h"], "lookback_h", 24, 720)
            else:
                horizons = portfolio["lookbacks_h"]
                if factor != "xsmom" or not isinstance(horizons, list) or not 2 <= len(horizons) <= 5:
                    raise ValueError("lookbacks_h richiede xsmom e 2..5 orizzonti")
                clean = [_strict_int(item, "lookbacks_h", 24, 720) for item in horizons]
                if clean != sorted(set(clean)):
                    raise ValueError("lookbacks_h deve essere unico e crescente")
            if factor == "tsmom" and portfolio.get("dollar_neutral") is not False:
                raise ValueError("tsmom richiede dollar_neutral=false")
            if factor == "tsmom" and {"long_q", "short_q", "vol_lookback_h"} & set(portfolio):
                raise ValueError("tsmom non accetta quantili o vol_lookback_h")
            if factor == "xsmom" and "vol_lookback_h" in portfolio:
                raise ValueError("xsmom non accetta vol_lookback_h")

    if factor != "tsmom":
        if not {"long_q", "short_q"} <= set(portfolio):
            raise ValueError("long_q e short_q sono obbligatori per i fattori cross-sectional")
        long_q = _finite_number(portfolio["long_q"], "long_q", 0.5, 0.9)
        short_q = _finite_number(portfolio["short_q"], "short_q", 0.1, 0.5)
        if long_q <= short_q:
            raise ValueError("long_q deve superare short_q")

    multiplier_cap = 1.0
    if "vol_target" in portfolio:
        vt = portfolio["vol_target"]
        if not isinstance(vt, dict) or set(vt) != VOL_TARGET_KEYS:
            raise ValueError("vol_target deve rispettare lo schema chiuso L2")
        if vt["enabled"] is not True:
            raise ValueError("vol_target presente richiede enabled=true")
        _finite_number(vt["target_vol_ann"], "target_vol_ann", 0.1, 0.5)
        _strict_int(vt["vol_window_h"], "vol_window_h", 240, 1440)
        floor = _finite_number(vt["gross_floor"], "gross_floor", 0.2, 0.6)
        multiplier_cap = _finite_number(vt["gross_cap"], "gross_cap", 1.0, 2.0)
        if floor > 1.0 or multiplier_cap < 1.0:
            raise ValueError("vol_target deve contenere 1.0 nel range floor/cap")
    risk_cap = _finite_number(
        (parent.get("risk") or {}).get("max_leverage"), "risk.max_leverage", 0.1, 4.0,
    )
    if gross * multiplier_cap > risk_cap + 1e-12:
        raise ValueError("gross effettivo supera risk.max_leverage del parent")


def _candidate_id(parent_id: str, pack_id: str) -> str:
    candidate_id = f"{family(parent_id)}-g{int(pack_id[:10], 16)}"
    if not ID_RE.fullmatch(candidate_id):
        raise ValueError("strategy id generato non valido")
    return candidate_id


def _materialize(proposal: dict, parent: dict, pack: dict) -> dict:
    spec = validate_portfolio(
        {"portfolio": deepcopy(proposal["portfolio"]), "thesis": proposal["thesis"]},
        deepcopy(parent),
        1,
    )
    symbols = _declared_symbols(parent)
    spec["id"] = _candidate_id(parent["id"], pack["pack_id"])
    spec["created"] = _parse_ts(pack["generated_at"]).date().isoformat()
    spec["status"] = "candidate"
    source_selection = (parent.get("universe") or {}).get("selection", "default")
    spec["universe"] = {"selection": "explicit"}
    spec["paper_symbols"] = ",".join(symbols)
    spec["evolution"] = {
        "mutable": ["portfolio"],
        "paper_universe": {
            "schema_version": 1,
            "source_parent_selection": source_selection,
            "symbols": symbols,
            "symbols_sha256": content_hash(symbols),
        },
        "notes": (
            f"Research OS L2 pack {pack['pack_id']}; one-shot mutation, "
            "frozen-data checker and human merge required."
        ),
    }
    if spec.get("risk") != parent.get("risk"):
        raise ValueError("risk mutato rispetto al parent")
    return spec


def _declared_symbols(parent: dict) -> list[str]:
    raw = parent.get("paper_symbols")
    symbols = raw if isinstance(raw, list) else str(raw or "").split(",")
    symbols = list(dict.fromkeys(str(symbol).strip() for symbol in symbols if str(symbol).strip()))
    cap = (parent.get("risk") or {}).get("max_concurrent_positions")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 3:
        raise ValueError("parent risk.max_concurrent_positions invalido")
    if not 3 <= len(symbols) <= cap:
        raise ValueError(
            f"paper_symbols deve contenere 3..{cap} asset, ricevuti {len(symbols)}"
        )
    return symbols


def _freeze_panel(candidate: dict, out: Path) -> dict:
    symbols = _declared_symbols(candidate)
    prices = panel(symbols, MONTHS)
    if list(prices.columns) != symbols:
        raise RuntimeError("panel non copre esattamente l'universo congelato")
    if (
        not isinstance(prices.index, pd.DatetimeIndex)
        or prices.index.tz is None
        or not prices.index.is_monotonic_increasing
    ):
        raise RuntimeError("panel richiede DatetimeIndex crescente")
    if prices.index.has_duplicates or len(prices) < MIN_PANEL_ROWS:
        raise RuntimeError(f"panel non copre sei mesi orari: {prices.shape}")
    tail = prices.tail(MIN_PANEL_ROWS)
    if not (tail.index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all():
        raise RuntimeError("panel non ha cadenza oraria continua")
    numeric = tail.apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy()).all() or (numeric <= 0).any().any():
        raise RuntimeError("panel contiene prezzi mancanti, non finiti o non positivi")
    prices = numeric
    data_path = out / "data" / "panel.parquet"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    prices.to_parquet(data_path)
    manifest = {
        "schema_version": 1,
        "kind": "strategy-evolution-frozen-panel.v1",
        "months": MONTHS,
        "symbols": list(prices.columns),
        "rows": len(prices),
        "start": str(prices.index.min()),
        "end": str(prices.index.max()),
        "path": "data/panel.parquet",
        "sha256": _sha256(data_path),
        "bytes": data_path.stat().st_size,
    }
    _write_json(out / "data-manifest.json", manifest)
    return manifest


def _load_panel(root: Path, manifest: dict) -> pd.DataFrame:
    manifest = _expect_keys(
        manifest,
        {
            "schema_version", "kind", "months", "symbols", "rows", "start", "end",
            "path", "sha256", "bytes",
        },
        "data manifest",
    )
    if (
        manifest["schema_version"] != 1
        or manifest["kind"] != "strategy-evolution-frozen-panel.v1"
        or manifest["months"] != MONTHS
        or manifest["path"] != "data/panel.parquet"
        or type(manifest["rows"]) is not int
        or manifest["rows"] < MIN_PANEL_ROWS
        or type(manifest["bytes"]) is not int
        or manifest["bytes"] <= 0
        or not isinstance(manifest["symbols"], list)
        or any(not isinstance(item, str) or not item for item in manifest["symbols"])
        or len(set(manifest["symbols"])) != len(manifest["symbols"])
        or not re.fullmatch(r"[0-9a-f]{64}", str(manifest["sha256"]))
    ):
        raise ValueError("data manifest values mismatch")
    path = (root / manifest["path"]).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("panel fuori bundle o mancante")
    if _sha256(path) != manifest["sha256"] or path.stat().st_size != manifest["bytes"]:
        raise ValueError("panel hash/size mismatch")
    prices = pd.read_parquet(path)
    if len(prices) != manifest["rows"] or list(prices.columns) != manifest["symbols"]:
        raise ValueError("panel schema mismatch")
    if (
        not isinstance(prices.index, pd.DatetimeIndex)
        or prices.index.tz is None
        or prices.index.has_duplicates
    ):
        raise ValueError("panel index mismatch")
    if not prices.index.is_monotonic_increasing or len(prices) < MIN_PANEL_ROWS:
        raise ValueError("panel span insufficiente")
    if not (prices.index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all():
        raise ValueError("panel cadence mismatch")
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("panel values mismatch")
    if str(prices.index.min()) != manifest["start"] or str(prices.index.max()) != manifest["end"]:
        raise ValueError("panel bounds mismatch")
    return prices


def _return_metrics(returns: pd.Series) -> dict:
    returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        return {"observations": 0, "sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0}
    equity = (1.0 + returns).cumprod()
    std = float(returns.std(ddof=1))
    sharpe = float(returns.mean() / std * np.sqrt(PPY)) if std > 0 else 0.0
    return {
        "observations": len(returns),
        "sharpe": round(sharpe, 4),
        "total_return": round(float(equity.iloc[-1] - 1.0), 6),
        "max_drawdown": round(float((equity / equity.cummax() - 1.0).min()), 6),
    }


def _evaluate_pair(parent: dict, candidate: dict, prices: pd.DataFrame, n_trials: int) -> dict:
    parent_full, parent_returns = eval_portfolio(parent, prices, MONTHS)
    candidate_full, candidate_returns = eval_portfolio(candidate, prices, MONTHS)
    tail_start = prices.index[len(prices) * 2 // 3]
    candidate_tail = candidate_returns.loc[candidate_returns.index >= tail_start]
    parent_tail = parent_returns.loc[parent_returns.index >= tail_start]
    if not candidate_tail.index.equals(parent_tail.index):
        raise RuntimeError("parent/candidate tail timestamps mismatch")
    candidate_oos = _return_metrics(candidate_tail)
    parent_oos = _return_metrics(parent_tail)
    dsr = deflated_sharpe(candidate_returns, n_trials=max(2, n_trials))
    gates = {
        "enough_oos_observations": candidate_oos["observations"] >= MIN_OOS_OBS,
        "positive_full_sharpe": candidate_full["sharpe"] > 0,
        "dsr_at_least_095": dsr["dsr"] >= MIN_DSR,
        "positive_oos_return": candidate_oos["total_return"] > 0,
        "oos_drawdown_within_30pct": candidate_oos["max_drawdown"] >= MAX_OOS_DRAWDOWN,
        "oos_sharpe_beats_parent": (
            candidate_oos["sharpe"] >= parent_oos["sharpe"] + MIN_OOS_SHARPE_EDGE
        ),
        "enough_rebalances": candidate_full["rebalances"] >= MIN_REBALANCES,
    }
    return {
        "kind": "development-tail-oos-proxy-not-official-holdout",
        "months": MONTHS,
        "n_trials": max(2, n_trials),
        "parent": {"id": parent["id"], "full": parent_full, "oos": parent_oos},
        "candidate": {"id": candidate["id"], "full": candidate_full, "oos": candidate_oos},
        "dsr": {key: round(value, 6) if isinstance(value, float) else value for key, value in dsr.items()},
        "gates": gates,
        "gate_pass": all(gates.values()),
    }


def _copy_research(source: Path, out: Path) -> None:
    research = out / "research"
    research.mkdir(parents=True, exist_ok=True)
    for source_path, name in (
        (source / "research" / "pack.json", "pack.json"),
        (source / "research" / "maker.json", "maker.json"),
        (source / "checker.json", "checker.json"),
    ):
        shutil.copy2(source_path, research / name)


def maker_context(input_dir: str | Path) -> dict:
    """Return the bounded context the OpenRouter Maker may inspect."""
    pack, research_maker, _ = _load_approved_research(Path(input_dir))
    return {
        "pack_id": pack["pack_id"],
        "preregistration": research_maker["candidate"],
        "parents": _parent_inventory(_active_parents()),
        "contract_path": "prompts/research_os/evolution-contracts.md",
    }


def _provider_metadata(path: Path, role: str) -> dict:
    value = _expect_keys(
        _read_json(path),
        {"role", "model", "created_at", "usage", "search_result_count"},
        f"{role} provider metadata",
    )
    if value["role"] != role or value["model"] != OPENROUTER_CONTROL_PLANE:
        raise ValueError(f"{role}: provider/model non autorizzato")
    _parse_ts(value["created_at"])
    if not isinstance(value["usage"], dict) or not isinstance(value["search_result_count"], int):
        raise ValueError(f"{role}: metadata provider invalida")
    return value


def _write_provider_metadata(path: Path, role: str, model: str, usage: dict, search: list) -> None:
    _write_json(path, {
        "role": role,
        "model": f"openrouter:{model}",
        "created_at": _now().isoformat(),
        "usage": usage,
        "search_result_count": len(search),
    })


def generate_openrouter_proposal(input_dir: str | Path, out_dir: str | Path) -> dict:
    context = maker_context(input_dir)
    contract = (ROOT / "prompts/research_os/evolution-contracts.md").read_text(
        encoding="utf-8"
    )
    prompt = (
        "Sei l'Evolution Maker L2. Produci una sola mutazione one-shot oppure BLOCKED. "
        "Non hai accesso ai dati del nuovo backtest. Non introdurre segnali, codice, fonti, "
        "universi o risk knob; usa soltanto il registry chiuso del contratto. La proposta deve "
        "implementare fedelmente la preregistrazione, non inseguire un risultato.\n\n"
        f"CONTRATTO:\n{contract}\n\nCONTESTO IMMUTABILE:\n{_canonical_json(context)}"
    )
    value, search, usage, model = research_cloud._openrouter_chat(
        prompt,
        search_prompt=(
            "Non cercare nuove idee o fonti. Limita il giudizio al mapping tecnico tra la "
            "preregistrazione e il registry portfolio fornito."
        ),
        timeout=600,
        enable_web=False,
    )
    proposal = _validate_proposal(value, _active_parents())
    out = Path(out_dir)
    _write_json(out / "proposal.json", proposal)
    _write_provider_metadata(out / "proposal-metadata.json", "evolution-maker", model, usage, search)
    return proposal


def run_maker(
    input_dir: str | Path,
    out_dir: str | Path,
    proposal_file: str | Path,
    provider_metadata_file: str | Path,
) -> dict:
    source, out = Path(input_dir), Path(out_dir)
    pack, _, research_checker = _load_approved_research(source)
    parents = _active_parents()
    proposal_path = Path(proposal_file)
    provider_path = Path(provider_metadata_file)
    provider = _provider_metadata(provider_path, "evolution-maker")
    proposal = _validate_proposal(_read_json(proposal_path), parents)
    run_id = f"evolution-maker-{uuid.uuid4().hex}"

    _copy_research(source, out)
    if proposal_path.resolve() != (out / "proposal.json").resolve():
        shutil.copy2(proposal_path, out / "proposal.json")
    if provider_path.resolve() != (out / "proposal-metadata.json").resolve():
        shutil.copy2(provider_path, out / "proposal-metadata.json")
    maker = {
        "kind": MAKER_KIND,
        "pack_id": pack["pack_id"],
        "research_checker_sha256": content_hash(research_checker),
        "proposal_sha256": _sha256(out / "proposal.json"),
        "provider_metadata_sha256": _sha256(out / "proposal-metadata.json"),
        "repo_commit": _repo_commit(),
        "created_at": _now().isoformat(),
        "maker_run_id": run_id,
        "control_plane": provider["model"],
        "outcome": proposal["outcome"],
        "blockers": proposal["blockers"],
        "parent": None,
        "candidate": None,
        "guardrails": dict(GUARDRAILS),
    }
    if proposal["outcome"] == "CANDIDATE":
        parent = parents[proposal["parent_id"]]
        candidate = _materialize(proposal, parent, pack)
        _write_yaml(out / "parent.yaml", parent)
        manifest = _freeze_panel(candidate, out)
        prices = _load_panel(out, manifest)
        report = _evaluate_pair(parent, candidate, prices, len(all_specs()) + 1)
        candidate["backtest"] = {"evolution_v1": report}
        _write_yaml(out / "candidate.yaml", candidate)
        maker["parent"] = {
            "strategy_id": parent["id"],
            "path": "parent.yaml",
            "sha256": _sha256(out / "parent.yaml"),
        }
        maker["candidate"] = {
            "strategy_id": candidate["id"],
            "path": "candidate.yaml",
            "sha256": _sha256(out / "candidate.yaml"),
            "logic_sha256": strategy_logic_sha256(candidate),
            "data_manifest_sha256": content_hash(manifest),
            "report": report,
        }
    _write_json(out / "maker.json", maker)
    _write_json(out / "metadata.json", {
        "role": "evolution-maker", "run_id": run_id,
        "control_plane": provider["model"], "created_at": _now().isoformat(),
        "guardrails": dict(GUARDRAILS),
    })
    return {"pack_id": pack["pack_id"], "outcome": maker["outcome"], "run_id": run_id}


def run_openrouter_maker(input_dir: str | Path, out_dir: str | Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="alphazero-evolution-maker-") as temp:
        generate_openrouter_proposal(input_dir, temp)
        return run_maker(
            input_dir,
            out_dir,
            Path(temp) / "proposal.json",
            Path(temp) / "proposal-metadata.json",
        )


def _verify_maker_bundle(source: Path) -> tuple[dict, dict, dict, dict, dict | None]:
    pack = _read_json(source / "research" / "pack.json")
    research_maker = _read_json(source / "research" / "maker.json")
    research_checker = _read_json(source / "research" / "checker.json")
    research_pack.validate_checker(
        pack, research_maker, research_checker,
        now=_parse_ts(research_checker.get("checked_at")),
    )
    maker = _expect_keys(
        _read_json(source / "maker.json"),
        {
            "kind", "pack_id", "research_checker_sha256", "created_at", "maker_run_id",
            "proposal_sha256", "provider_metadata_sha256", "repo_commit", "control_plane",
            "outcome", "blockers", "parent", "candidate", "guardrails",
        },
        "evolution maker",
    )
    if maker["kind"] != MAKER_KIND or maker["pack_id"] != pack["pack_id"]:
        raise ValueError("Evolution Maker kind/pack mismatch")
    if not re.fullmatch(r"[0-9a-f]{40}", maker["repo_commit"]):
        raise ValueError("Evolution Maker repo_commit invalido")
    proposal_path = source / "proposal.json"
    if _sha256(proposal_path) != maker["proposal_sha256"]:
        raise ValueError("proposal hash mismatch")
    provider_path = source / "proposal-metadata.json"
    provider = _provider_metadata(provider_path, "evolution-maker")
    if _sha256(provider_path) != maker["provider_metadata_sha256"]:
        raise ValueError("proposal provider metadata hash mismatch")
    if maker["control_plane"] != OPENROUTER_CONTROL_PLANE or provider["model"] != maker["control_plane"]:
        raise ValueError("Evolution Maker control plane non ammesso")
    if maker["research_checker_sha256"] != content_hash(research_checker):
        raise ValueError("research checker hash mismatch")
    if maker["guardrails"] != GUARDRAILS:
        raise ValueError("guardrails Evolution Maker mismatch")
    if maker["outcome"] == "BLOCKED":
        proposal = _validate_proposal(_read_json(proposal_path), {})
        if not maker["blockers"] or maker["parent"] is not None or maker["candidate"] is not None:
            raise ValueError("Evolution Maker BLOCKED incoerente")
        if proposal["outcome"] != "BLOCKED" or proposal["blockers"] != maker["blockers"]:
            raise ValueError("Evolution Maker BLOCKED/proposal mismatch")
        return pack, research_maker, research_checker, maker, None
    if maker["outcome"] != "CANDIDATE" or maker["blockers"]:
        raise ValueError("Evolution Maker outcome incoerente")
    parent_meta = _expect_keys(maker["parent"], {"strategy_id", "path", "sha256"}, "parent")
    candidate_meta = _expect_keys(
        maker["candidate"],
        {
            "strategy_id", "path", "sha256", "logic_sha256",
            "data_manifest_sha256", "report",
        },
        "candidate",
    )
    parent_path, candidate_path = source / parent_meta["path"], source / candidate_meta["path"]
    if _sha256(parent_path) != parent_meta["sha256"] or _sha256(candidate_path) != candidate_meta["sha256"]:
        raise ValueError("parent/candidate file hash mismatch")
    parent = yaml.safe_load(parent_path.read_text(encoding="utf-8"))
    candidate = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    if parent.get("id") != parent_meta["strategy_id"] or candidate.get("id") != candidate_meta["strategy_id"]:
        raise ValueError("parent/candidate id mismatch")
    if strategy_logic_sha256(candidate) != candidate_meta["logic_sha256"]:
        raise ValueError("candidate logic hash mismatch")
    if candidate.get("status") != "candidate" or candidate.get("parent") != parent.get("id"):
        raise ValueError("candidate lifecycle mismatch")
    if candidate.get("risk") != parent.get("risk"):
        raise ValueError("candidate risk non immutabile")
    proposal = _validate_proposal(_read_json(proposal_path), {parent["id"]: parent})
    if proposal["outcome"] != "CANDIDATE" or proposal["parent_id"] != parent["id"]:
        raise ValueError("proposal/candidate lineage mismatch")
    expected_candidate = _materialize(proposal, parent, pack)
    actual_without_backtest = deepcopy(candidate)
    actual_without_backtest.pop("backtest", None)
    if actual_without_backtest != expected_candidate:
        raise ValueError("candidate non riproducibile dal proposal")
    _validate_l2_portfolio(candidate.get("portfolio"), parent)
    validated = validate_portfolio(
        {"portfolio": deepcopy(candidate.get("portfolio")), "thesis": candidate.get("thesis")},
        deepcopy(parent),
        1,
    )
    for field in (
        "engine", "timeframe", "decision_every_h", "signals", "exit", "risk",
        "portfolio", "thesis", "parent",
    ):
        if candidate.get(field) != validated.get(field):
            raise ValueError(f"candidate field non valido: {field}")
    symbols = _declared_symbols(parent)
    if candidate.get("universe") != {"selection": "explicit"}:
        raise ValueError("candidate universe non congelato")
    if candidate.get("paper_symbols") != ",".join(symbols):
        raise ValueError("candidate paper_symbols non congelati")
    expected_pin = {
        "schema_version": 1,
        "source_parent_selection": (parent.get("universe") or {}).get("selection", "default"),
        "symbols": symbols,
        "symbols_sha256": content_hash(symbols),
    }
    evolution = candidate.get("evolution") or {}
    if evolution.get("paper_universe") != expected_pin:
        raise ValueError("candidate paper universe pin mismatch")
    manifest = _read_json(source / "data-manifest.json")
    if content_hash(manifest) != candidate_meta["data_manifest_sha256"]:
        raise ValueError("data manifest hash mismatch")
    if manifest.get("symbols") != symbols:
        raise ValueError("data manifest universe mismatch")
    return pack, research_maker, research_checker, maker, {
        "parent": parent, "candidate": candidate, "manifest": manifest,
    }


def _load_semantic_review(path: Path, maker_run_id: str) -> dict:
    value = _expect_keys(
        _read_json(path),
        {"maker_run_id", "reviewer", "verdict", "blockers", "notes", "checks"},
        "semantic review",
    )
    if value["maker_run_id"] != maker_run_id:
        raise ValueError("semantic review non legata al Maker")
    if not isinstance(value["reviewer"], str) or not value["reviewer"].strip():
        raise ValueError("semantic reviewer mancante")
    checks = _expect_keys(value["checks"], SEMANTIC_CHECKS, "semantic checks")
    if any(type(flag) is not bool for flag in checks.values()):
        raise ValueError("semantic checks non booleani")
    if value["verdict"] not in ("APPROVE", "REJECT"):
        raise ValueError("semantic verdict invalido")
    if not isinstance(value["blockers"], list) or any(
        not isinstance(item, str) or not item.strip() for item in value["blockers"]
    ):
        raise ValueError("semantic blockers invalidi")
    if not isinstance(value["notes"], str) or not value["notes"].strip():
        raise ValueError("semantic notes mancanti")
    if value["verdict"] == "APPROVE" and (value["blockers"] or not all(checks.values())):
        raise ValueError("semantic APPROVE incoerente")
    if value["verdict"] == "REJECT" and not value["blockers"]:
        raise ValueError("semantic REJECT richiede blocker")
    return value


def generate_openrouter_review(input_dir: str | Path, out_dir: str | Path) -> dict:
    source = Path(input_dir)
    _, research_maker, _, maker, bundle = _verify_maker_bundle(source)
    if bundle is None:
        context = {"maker": maker, "reason": "Maker BLOCKED"}
    else:
        context = {
            "preregistration": research_maker["candidate"],
            "parent": bundle["parent"],
            "candidate": bundle["candidate"],
            "deterministic_report": maker["candidate"]["report"],
        }
    prompt = (
        "Sei l'Evolution Checker L2 indipendente. Non modificare la proposta e non suggerire "
        "parametri alternativi. Cerca drift semantico: il mapping deve preservare la "
        "preregistrazione usando soltanto dati e fattori gia disponibili. Un backtest positivo "
        "non basta. Restituisci esattamente verdict, blockers, notes, checks; checks contiene "
        "prereg_alignment, mechanism_preserved, data_contract_supported e "
        "no_hindsight_or_new_code. APPROVE richiede tutti true e zero blocker.\n\n"
        f"BUNDLE IMMUTABILE:\n{_canonical_json(context)}"
    )
    value, search, usage, model = research_cloud._openrouter_chat(
        prompt,
        search_prompt=(
            "Non cercare nuove idee. Verifica soltanto il mapping tecnico e respingi qualsiasi "
            "dipendenza non presente nel bundle."
        ),
        timeout=480,
        enable_web=False,
    )
    value = _expect_keys(value, {"verdict", "blockers", "notes", "checks"}, "provider review")
    review = {
        "maker_run_id": maker["maker_run_id"],
        "reviewer": f"openrouter:{model}",
        **value,
    }
    out = Path(out_dir)
    _write_json(out / "review.json", review)
    _write_provider_metadata(out / "review-metadata.json", "evolution-checker", model, usage, search)
    return _load_semantic_review(out / "review.json", maker["maker_run_id"])


def run_checker(
    input_dir: str | Path,
    out_dir: str | Path,
    review_file: str | Path,
    provider_metadata_file: str | Path,
) -> dict:
    source, out = Path(input_dir), Path(out_dir)
    pack, _, _, maker, bundle = _verify_maker_bundle(source)
    shutil.copytree(source, out, dirs_exist_ok=True)
    review_path = Path(review_file)
    provider_path = Path(provider_metadata_file)
    provider = _provider_metadata(provider_path, "evolution-checker")
    semantic = _load_semantic_review(review_path, maker["maker_run_id"])
    if semantic["reviewer"] != provider["model"]:
        raise ValueError("semantic reviewer/provider mismatch")
    if review_path.resolve() != (out / "review.json").resolve():
        shutil.copy2(review_path, out / "review.json")
    if provider_path.resolve() != (out / "review-metadata.json").resolve():
        shutil.copy2(provider_path, out / "review-metadata.json")
    run_id = f"evolution-checker-{uuid.uuid4().hex}"
    blockers = list(maker["blockers"])
    report = None
    if bundle is not None:
        prices = _load_panel(source, bundle["manifest"])
        report = _evaluate_pair(
            bundle["parent"], bundle["candidate"], prices,
            maker["candidate"]["report"]["n_trials"],
        )
        if report != maker["candidate"]["report"]:
            blockers.append("recomputed report mismatch")
        elif not report["gate_pass"]:
            blockers.extend(name for name, passed in report["gates"].items() if not passed)
        else:
            blockers.extend(semantic["blockers"])
    approved = bundle is not None and not blockers and semantic is not None and semantic["verdict"] == "APPROVE"
    checker = {
        "kind": CHECKER_KIND,
        "pack_id": pack["pack_id"],
        "maker_sha256": content_hash(maker),
        "maker_run_id": maker["maker_run_id"],
        "checked_at": _now().isoformat(),
        "checker_run_id": run_id,
        "control_plane": provider["model"],
        "review_sha256": _sha256(out / "review.json"),
        "provider_metadata_sha256": _sha256(out / "review-metadata.json"),
        "verdict": APPROVE_VERDICT if approved else "REJECT",
        "approved_strategy_id": bundle["candidate"]["id"] if approved else None,
        "blockers": blockers,
        "semantic_review": semantic,
        "recomputed_report": report,
        "guardrails": dict(GUARDRAILS),
    }
    if checker["checker_run_id"] == checker["maker_run_id"]:
        raise ValueError("Maker e Checker L2 non indipendenti")
    if approved:
        approved_spec = deepcopy(bundle["candidate"])
        approved_spec["status"] = "challenger"
        _write_yaml(out / "approved.yaml", approved_spec)
        checker["approved_sha256"] = _sha256(out / "approved.yaml")
        checker["approved_logic_sha256"] = strategy_logic_sha256(approved_spec)
    else:
        checker["approved_sha256"] = None
        checker["approved_logic_sha256"] = None
    _write_json(out / "evolution-checker.json", checker)
    _write_json(out / "checker-metadata.json", {
        "role": "evolution-checker", "run_id": run_id,
        "control_plane": provider["model"],
        "reviewer": semantic["reviewer"], "created_at": _now().isoformat(),
        "guardrails": dict(GUARDRAILS),
    })
    return {"pack_id": pack["pack_id"], "verdict": checker["verdict"], "run_id": run_id}


def run_openrouter_checker(input_dir: str | Path, out_dir: str | Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="alphazero-evolution-checker-") as temp:
        generate_openrouter_review(input_dir, temp)
        return run_checker(
            input_dir,
            out_dir,
            Path(temp) / "review.json",
            Path(temp) / "review-metadata.json",
        )


def _write_once(path: Path, data: bytes) -> bool:
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f"collisione create-once: {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def _repo_family_challenger_ids(repo: Path, family_id: str) -> set[str]:
    """Read the PR registry and return one unique active challenger set."""
    ids: list[str] = []
    for directory in (repo / "strategies", repo / "strategies" / "generated"):
        for path in sorted(directory.glob("*.yaml")):
            if "candidates" in path.name:
                continue
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            strategy_id = value.get("id") if isinstance(value, dict) else None
            if not isinstance(strategy_id, str):
                raise ValueError(f"registry strategy invalida: {path}")
            if (
                value.get("engine") == "portfolio"
                and value.get("status") == "challenger"
                and family(strategy_id) == family_id
            ):
                ids.append(strategy_id)
    if len(ids) != len(set(ids)):
        raise ValueError(f"challenger duplicati nella famiglia {family_id}")
    return set(ids)


def publish(input_dir: str | Path, repo_root: str | Path) -> dict:
    source, repo = Path(input_dir), Path(repo_root)
    pack, _, _, maker, bundle = _verify_maker_bundle(source)
    checker = _read_json(source / "evolution-checker.json")
    required = {
        "kind", "pack_id", "maker_sha256", "maker_run_id", "checked_at",
        "checker_run_id", "control_plane", "review_sha256", "provider_metadata_sha256",
        "verdict", "approved_strategy_id", "blockers", "semantic_review",
        "recomputed_report", "guardrails", "approved_sha256", "approved_logic_sha256",
    }
    _expect_keys(checker, required, "evolution checker")
    if bundle is None or checker["kind"] != CHECKER_KIND or checker["pack_id"] != pack["pack_id"]:
        raise ValueError("checker bundle mismatch")
    if checker["verdict"] != APPROVE_VERDICT or checker["blockers"]:
        raise ValueError("publish richiede APPROVE_CHALLENGER_PR")
    if checker["maker_sha256"] != content_hash(maker) or checker["maker_run_id"] != maker["maker_run_id"]:
        raise ValueError("checker maker hash/id mismatch")
    if checker["checker_run_id"] == checker["maker_run_id"] or checker["guardrails"] != GUARDRAILS:
        raise ValueError("checker identity/guardrails mismatch")
    if checker["control_plane"] != OPENROUTER_CONTROL_PLANE:
        raise ValueError("checker control plane non ammesso")
    if _sha256(source / "review.json") != checker["review_sha256"]:
        raise ValueError("checker review hash mismatch")
    if _sha256(source / "review-metadata.json") != checker["provider_metadata_sha256"]:
        raise ValueError("checker provider metadata hash mismatch")
    semantic = checker["semantic_review"] or {}
    if (
        semantic.get("verdict") != "APPROVE"
        or set(semantic.get("checks", {})) != SEMANTIC_CHECKS
        or not all(semantic["checks"].values())
        or not checker["recomputed_report"].get("gate_pass")
    ):
        raise ValueError("checker approval non supportata da gate e review semantica")
    approved_path = source / "approved.yaml"
    approved = yaml.safe_load(approved_path.read_text(encoding="utf-8"))
    if _sha256(approved_path) != checker["approved_sha256"]:
        raise ValueError("approved spec hash mismatch")
    if strategy_logic_sha256(approved) != checker["approved_logic_sha256"]:
        raise ValueError("approved logic hash mismatch")
    if checker["approved_logic_sha256"] != maker["candidate"]["logic_sha256"]:
        raise ValueError("approved logic diverge dalla candidate Maker")
    if approved.get("id") != checker["approved_strategy_id"] or approved.get("status") != "challenger":
        raise ValueError("approved spec lifecycle mismatch")
    sid = approved["id"]

    _, current_parent = _repo_spec(repo, bundle["parent"]["id"])
    if current_parent.get("status") not in ("champion", "challenger"):
        raise ValueError("parent corrente non piu attivo")
    for field in PARENT_STABLE_FIELDS:
        if current_parent.get(field) != bundle["parent"].get(field):
            raise ValueError(f"parent corrente stale sul campo {field}")
    challenger_ids = _repo_family_challenger_ids(repo, family(sid))
    if len(challenger_ids | {sid}) > MAX_FAMILY_CHALLENGERS:
        raise ValueError(f"family challenger cap superato per {family(sid)}")

    evidence_dir = repo / "evidence" / "evolution" / sid
    writes = {
        repo / "strategies" / "generated" / f"{sid}.yaml": approved_path.read_bytes(),
        evidence_dir / "research-pack.json": (source / "research" / "pack.json").read_bytes(),
        evidence_dir / "research-maker.json": (source / "research" / "maker.json").read_bytes(),
        evidence_dir / "research-checker.json": (source / "research" / "checker.json").read_bytes(),
        evidence_dir / "proposal.json": (source / "proposal.json").read_bytes(),
        evidence_dir / "proposal-metadata.json": (source / "proposal-metadata.json").read_bytes(),
        evidence_dir / "parent.yaml": (source / "parent.yaml").read_bytes(),
        evidence_dir / "maker.json": (json.dumps(maker, indent=2, ensure_ascii=False) + "\n").encode(),
        evidence_dir / "review.json": (source / "review.json").read_bytes(),
        evidence_dir / "review-metadata.json": (source / "review-metadata.json").read_bytes(),
        evidence_dir / "checker.json": (json.dumps(checker, indent=2, ensure_ascii=False) + "\n").encode(),
        evidence_dir / "data-manifest.json": (json.dumps(bundle["manifest"], indent=2, ensure_ascii=False) + "\n").encode(),
    }
    changed = [str(path.relative_to(repo)) for path, data in writes.items() if _write_once(path, data)]
    return {"pack_id": pack["pack_id"], "strategy_id": sid, "changed_paths": changed}


PARENT_STABLE_FIELDS = {
    "engine", "universe", "paper_symbols", "timeframe", "decision_every_h",
    "signals", "exit", "risk", "portfolio",
}


def _repo_spec(repo: Path, strategy_id: str) -> tuple[Path, dict]:
    matches = []
    for directory in (repo / "strategies", repo / "strategies" / "generated"):
        for path in sorted(directory.glob("*.yaml")):
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("id") == strategy_id:
                matches.append((path, value))
    if len(matches) != 1:
        raise ValueError(f"strategy id {strategy_id}: atteso un solo file, trovati {len(matches)}")
    return matches[0]


def _validate_published_one(
    repo: Path, evidence_dir: Path, *, require_current_admission: bool = False,
) -> str:
    strategy_id = evidence_dir.name
    strategy_path, strategy = _repo_spec(repo, strategy_id)
    maker = _read_json(evidence_dir / "maker.json")
    checker = _read_json(evidence_dir / "checker.json")
    manifest = _read_json(evidence_dir / "data-manifest.json")
    proposal_path = evidence_dir / "proposal.json"
    proposal_metadata_path = evidence_dir / "proposal-metadata.json"
    review_path = evidence_dir / "review.json"
    review_metadata_path = evidence_dir / "review-metadata.json"
    parent_path = evidence_dir / "parent.yaml"
    parent = yaml.safe_load(parent_path.read_text(encoding="utf-8"))

    if checker.get("verdict") != APPROVE_VERDICT or checker.get("blockers"):
        raise ValueError(f"{strategy_id}: checker non approvato")
    if checker.get("approved_strategy_id") != strategy_id:
        raise ValueError(f"{strategy_id}: checker strategy id mismatch")
    allowed_statuses = {"challenger"} if require_current_admission else HISTORICAL_LIFECYCLE_STATUSES
    if strategy.get("status") not in allowed_statuses:
        raise ValueError(f"{strategy_id}: lifecycle pubblicato invalido")
    admission_strategy = deepcopy(strategy)
    admission_strategy["status"] = "challenger"
    admission_sha256 = hashlib.sha256(_yaml_bytes(admission_strategy)).hexdigest()
    if admission_sha256 != checker.get("approved_sha256"):
        raise ValueError(f"{strategy_id}: approved spec hash mismatch")
    logic_hash = strategy_logic_sha256(strategy)
    if logic_hash != checker.get("approved_logic_sha256"):
        raise ValueError(f"{strategy_id}: approved logic hash mismatch")
    if logic_hash != (maker.get("candidate") or {}).get("logic_sha256"):
        raise ValueError(f"{strategy_id}: Maker logic mismatch")
    if _sha256(parent_path) != (maker.get("parent") or {}).get("sha256"):
        raise ValueError(f"{strategy_id}: parent snapshot hash mismatch")
    if _sha256(proposal_path) != maker.get("proposal_sha256"):
        raise ValueError(f"{strategy_id}: proposal hash mismatch")
    if _sha256(proposal_metadata_path) != maker.get("provider_metadata_sha256"):
        raise ValueError(f"{strategy_id}: proposal provider metadata mismatch")
    if _sha256(review_path) != checker.get("review_sha256"):
        raise ValueError(f"{strategy_id}: review hash mismatch")
    if _sha256(review_metadata_path) != checker.get("provider_metadata_sha256"):
        raise ValueError(f"{strategy_id}: review provider metadata mismatch")
    proposal_provider = _provider_metadata(proposal_metadata_path, "evolution-maker")
    review_provider = _provider_metadata(review_metadata_path, "evolution-checker")
    if maker.get("control_plane") != proposal_provider["model"]:
        raise ValueError(f"{strategy_id}: Maker provider mismatch")
    if checker.get("control_plane") != review_provider["model"]:
        raise ValueError(f"{strategy_id}: Checker provider mismatch")
    if content_hash(manifest) != (maker.get("candidate") or {}).get("data_manifest_sha256"):
        raise ValueError(f"{strategy_id}: manifest hash mismatch")

    research_pack_value = _read_json(evidence_dir / "research-pack.json")
    research_maker = _read_json(evidence_dir / "research-maker.json")
    research_checker = _read_json(evidence_dir / "research-checker.json")
    research_pack.validate_checker(
        research_pack_value, research_maker, research_checker,
        now=_parse_ts(research_checker.get("checked_at")),
    )
    if content_hash(research_checker) != maker.get("research_checker_sha256"):
        raise ValueError(f"{strategy_id}: research checker lineage mismatch")

    if strategy.get("parent") != parent.get("id"):
        raise ValueError(f"{strategy_id}: lifecycle pubblicato invalido")
    if require_current_admission:
        _, current_parent = _repo_spec(repo, parent.get("id"))
        if current_parent.get("status") not in ("champion", "challenger"):
            raise ValueError(f"{strategy_id}: parent non piu attivo")
        for field in PARENT_STABLE_FIELDS:
            if current_parent.get(field) != parent.get(field):
                raise ValueError(f"{strategy_id}: parent stale sul campo {field}")
        if len(_repo_family_challenger_ids(repo, family(strategy_id))) > MAX_FAMILY_CHALLENGERS:
            raise ValueError(f"{strategy_id}: family challenger cap superato")
    symbols = _declared_symbols(strategy)
    pin = (strategy.get("evolution") or {}).get("paper_universe")
    if not isinstance(pin, dict) or pin.get("symbols") != symbols:
        raise ValueError(f"{strategy_id}: paper universe pin invalido")
    if pin.get("symbols_sha256") != content_hash(symbols) or manifest.get("symbols") != symbols:
        raise ValueError(f"{strategy_id}: paper universe evidence mismatch")
    semantic = checker.get("semantic_review") or {}
    if (
        semantic.get("verdict") != "APPROVE"
        or set(semantic.get("checks", {})) != SEMANTIC_CHECKS
        or not all(semantic["checks"].values())
        or not (checker.get("recomputed_report") or {}).get("gate_pass")
    ):
        raise ValueError(f"{strategy_id}: gate pubblicato invalido")
    return strategy_id


def validate_published(
    repo_root: str | Path,
    strategy_id: str | None = None,
    *,
    require_current_admission: bool = False,
) -> list[str]:
    repo = Path(repo_root)
    evidence_root = repo / "evidence" / "evolution"
    if strategy_id is not None:
        directories = [evidence_root / strategy_id]
    else:
        directories = sorted(path for path in evidence_root.glob("*") if path.is_dir())
    return [
        _validate_published_one(
            repo, path, require_current_admission=require_current_admission,
        )
        for path in directories
    ]


def validate_changed_admissions(repo_root: str | Path, base_ref: str) -> list[str]:
    """Strictly recheck evidence directories introduced since ``base_ref``."""
    repo = Path(repo_root)
    result = subprocess.run(
        [
            "git", "diff", "--diff-filter=A", "--name-only", base_ref, "HEAD", "--",
            "evidence/evolution",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )
    strategy_ids = set()
    for raw_path in result.stdout.splitlines():
        parts = Path(raw_path).parts
        if len(parts) < 4 or parts[:2] != ("evidence", "evolution"):
            continue
        strategy_id = parts[2]
        if not ID_RE.fullmatch(strategy_id):
            raise ValueError(f"strategy id evidence invalido: {strategy_id}")
        strategy_ids.add(strategy_id)
    validated = []
    for strategy_id in sorted(strategy_ids):
        validated.extend(validate_published(
            repo,
            strategy_id,
            require_current_admission=True,
        ))
    return validated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    maker = commands.add_parser("maker")
    maker.add_argument("--input-dir", required=True)
    maker.add_argument("--out-dir", required=True)
    maker.add_argument("--proposal-file", required=True)
    maker.add_argument("--provider-metadata-file", required=True)
    remote_maker = commands.add_parser("openrouter-maker")
    remote_maker.add_argument("--input-dir", required=True)
    remote_maker.add_argument("--out-dir", required=True)
    context = commands.add_parser("context")
    context.add_argument("--input-dir", required=True)
    context.add_argument("--out-file")
    checker = commands.add_parser("checker")
    checker.add_argument("--input-dir", required=True)
    checker.add_argument("--out-dir", required=True)
    checker.add_argument("--review-file", required=True)
    checker.add_argument("--provider-metadata-file", required=True)
    remote_checker = commands.add_parser("openrouter-checker")
    remote_checker.add_argument("--input-dir", required=True)
    remote_checker.add_argument("--out-dir", required=True)
    publisher = commands.add_parser("publish")
    publisher.add_argument("--input-dir", required=True)
    publisher.add_argument("--repo-root", required=True)
    publisher.add_argument("--result-file")
    validator = commands.add_parser("validate-published")
    validator.add_argument("--repo-root", default=".")
    validator.add_argument("--strategy-id")
    validator.add_argument("--require-current-admission", action="store_true")
    changed_validator = commands.add_parser("validate-changed-admissions")
    changed_validator.add_argument("--repo-root", default=".")
    changed_validator.add_argument("--base-ref", required=True)
    args = parser.parse_args()
    if args.command == "maker":
        result = run_maker(
            args.input_dir,
            args.out_dir,
            args.proposal_file,
            args.provider_metadata_file,
        )
    elif args.command == "openrouter-maker":
        result = run_openrouter_maker(args.input_dir, args.out_dir)
    elif args.command == "context":
        result = maker_context(args.input_dir)
        if args.out_file:
            _write_json(Path(args.out_file), result)
    elif args.command == "checker":
        result = run_checker(
            args.input_dir,
            args.out_dir,
            args.review_file,
            args.provider_metadata_file,
        )
    elif args.command == "openrouter-checker":
        result = run_openrouter_checker(args.input_dir, args.out_dir)
    elif args.command == "publish":
        result = publish(args.input_dir, args.repo_root)
        if args.result_file:
            _write_json(Path(args.result_file), result)
    elif args.command == "validate-published":
        result = {"validated_strategy_ids": validate_published(
            args.repo_root,
            args.strategy_id,
            require_current_admission=args.require_current_admission,
        )}
    else:
        result = {"validated_strategy_ids": validate_changed_admissions(
            args.repo_root, args.base_ref,
        )}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
