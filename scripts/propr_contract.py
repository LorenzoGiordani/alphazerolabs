"""Frozen contract for the authorized Propr Free Trial paper lane."""

SPEC_REL = "strategies/generated/xsmom-multihorizon-v1.yaml"
STRATEGY_ID = "xsmom-multihorizon-v1"
EXPECTED_CHALLENGE_SLUG = "free-trial"
EXPECTED_INITIAL_BALANCE = 5000

RULEBOOK = {
    "version": "1.0.4",
    "source": "https://www.propr.xyz/rules",
    "profit_target_pct": 10,
    "max_daily_loss_pct": 3,
    "daily_loss_allowance_formula": (
        "0.03 * max(starting_balance, day_start_realized_balance)"
    ),
    "daily_reset": "00:00 UTC",
    "max_drawdown_pct": 6,
    "drawdown_type": "static",
}

PROPR_GROSS_OVERRIDE = 0.3
PROPR_DAILY_STOP_PCT = 0.02
PROPR_TRANCHE_H = 24
AUTOMANAGE_VERSION = "systematic-paper-automanage-v1"
MAX_ORDERS_PER_ACTION = 12

GUARD_VERSION = "propr-guard-v2"
GUARD_STOP_DISTANCE = 0.04
GUARD_MAX_CREATES = 8

TRUSTED_PATHS = (
    ".github/workflows/paper-run.yml",
    "backtest/evidence.py",
    "backtest/portfolio.py",
    "backtest/strategy.py",
    "pipeline/live.py",
    "pyproject.toml",
    "scripts/portfolio_paper.py",
    "scripts/propr_client.py",
    "scripts/propr_contract.py",
    "scripts/propr_guard.py",
    "scripts/propr_paper.py",
    SPEC_REL,
    "uv.lock",
)


def execution_contract(spec: dict) -> dict:
    portfolio = spec.get("portfolio") or {}
    return {
        "strategy_id": spec.get("id"),
        "strategy_path": SPEC_REL,
        "strategy_status": spec.get("status"),
        "engine": spec.get("engine"),
        "paper_symbols": str(spec.get("paper_symbols", "")).split(","),
        "lookbacks_h": portfolio.get("lookbacks_h"),
        "rebalance_h": portfolio.get("rebalance_h"),
        "dollar_neutral": portfolio.get("dollar_neutral"),
        "automanage_version": AUTOMANAGE_VERSION,
        "gross_override": PROPR_GROSS_OVERRIDE,
        "daily_stop_pct": PROPR_DAILY_STOP_PCT,
        "tranche_h": PROPR_TRANCHE_H,
        "max_orders_per_action": MAX_ORDERS_PER_ACTION,
        "max_leverage": (spec.get("risk") or {}).get("max_leverage"),
        "sizing_base": "challenge_initial_balance",
        "guard_version": GUARD_VERSION,
        "guard_stop_distance_pct": GUARD_STOP_DISTANCE * 100,
        "guard_max_creates": GUARD_MAX_CREATES,
        "requires_guard": True,
        "requires_account_pin": True,
        "rulebook": RULEBOOK,
    }
