import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.propr_turbo_risk import (  # noqa: E402
    DailySnapshot,
    EquityObservation,
    OrderGate,
    RiskMemory,
    RiskState,
    TURBO_10K_PROFILE,
    evaluate_post_entry,
    evaluate_risk,
)


ACCOUNT = "turbo-10k-1"
NOW = datetime(2026, 7, 23, 12, tzinfo=timezone.utc)
MIDNIGHT = datetime(2026, 7, 23, tzinfo=timezone.utc)


def _snapshot(*, realized="10000", equity="10000", account=ACCOUNT, at=MIDNIGHT):
    return DailySnapshot(
        account_id=account,
        as_of_utc=at,
        day_start_realized_balance=Decimal(realized),
        day_start_equity=Decimal(equity),
    )


def _observation(
    *,
    balance="10000",
    equity="10000",
    cost="40",
    account=ACCOUNT,
    at=None,
):
    return EquityObservation(
        account_id=account,
        observed_at_utc=at or NOW,
        realized_balance=Decimal(balance),
        equity=Decimal(equity),
        stressed_flatten_cost=Decimal(cost),
    )


def _evaluate(*, snapshot=None, observation=None, memory=RiskMemory(), **kwargs):
    return evaluate_risk(
        expected_account_id=ACCOUNT,
        now_utc=NOW,
        snapshot=_snapshot() if snapshot is None else snapshot,
        observation=_observation() if observation is None else observation,
        memory=memory,
        **kwargs,
    )


def _post(
    decision,
    equity,
    *,
    account=ACCOUNT,
    now=NOW,
    max_age=timedelta(seconds=2),
):
    return evaluate_post_entry(
        decision,
        equity,
        expected_account_id=account,
        now_utc=now,
        max_age=max_age,
    )


def test_turbo_10k_profile_is_frozen():
    assert TURBO_10K_PROFILE.starting_balance == Decimal("10000")
    assert TURBO_10K_PROFILE.target_balance == Decimal("10900")
    assert TURBO_10K_PROFILE.static_floor == Decimal("9700")
    assert TURBO_10K_PROFILE.daily_loss_pct == Decimal("0.03")


def test_baseline_floors_and_reserve_are_exact_decimals():
    decision = _evaluate(observation=_observation(equity="9900", cost="40"))

    assert decision.daily_allowance == Decimal("300.00")
    assert decision.daily_floor == Decimal("9700.00")
    assert decision.hard_floor == Decimal("9700")
    assert decision.account_id == ACCOUNT
    assert decision.evaluated_at_utc == NOW
    assert decision.target_balance == Decimal("10900")
    assert decision.realized_balance == Decimal("10000")
    assert decision.day_start_realized_balance == Decimal("10000")
    assert decision.day_start_equity == Decimal("10000")
    assert decision.observed_equity == Decimal("9900")
    assert decision.stressed_flatten_cost == Decimal("40")
    assert decision.target_reached is False
    assert decision.liquidation_adjusted_equity == Decimal("9860")
    assert decision.exit_reserve == Decimal("100")
    assert decision.soft_floor == Decimal("9800")
    assert decision.state is RiskState.ACTIVE
    assert decision.order_gate is OrderGate.ALLOW_NEW_ORDERS


def test_hard_floor_equal_is_permanent_halt():
    decision = _evaluate(observation=_observation(equity="9700"))

    assert decision.state is RiskState.HALT_ACCOUNT
    assert decision.order_gate is OrderGate.NO_NEW_ORDERS
    assert decision.reason == "hard_floor_touch"


def test_day_start_equity_at_or_below_hard_floor_halts_even_after_recovery():
    equal = _evaluate(
        snapshot=_snapshot(equity="9700"),
        observation=_observation(equity="10000", cost="0"),
    )
    below = _evaluate(
        snapshot=_snapshot(equity="9699.99"),
        observation=_observation(equity="10000", cost="0"),
    )

    for decision in (equal, below):
        assert decision.state is RiskState.HALT_ACCOUNT
        assert decision.order_gate is OrderGate.NO_NEW_ORDERS
        assert decision.reason == "day_start_hard_floor_touch"


def test_soft_floor_equal_locks_today_and_one_cent_above_is_active():
    equal = _evaluate(observation=_observation(equity="9800", cost="0"))
    above = _evaluate(observation=_observation(equity="9800.01", cost="0"))

    assert equal.state is RiskState.LOCKED_TODAY
    assert equal.order_gate is OrderGate.NO_NEW_ORDERS
    assert above.state is RiskState.ACTIVE
    assert above.order_gate is OrderGate.ALLOW_NEW_ORDERS


def test_profitable_day_keeps_fixed_starting_balance_allowance():
    decision = _evaluate(
        snapshot=_snapshot(realized="10500", equity="10400"),
        observation=_observation(equity="10400", cost="125"),
    )

    assert decision.daily_allowance == Decimal("300.00")
    assert decision.daily_floor == Decimal("10100.00")
    assert decision.hard_floor == Decimal("10100.00")
    assert decision.liquidation_adjusted_equity == Decimal("10275")
    assert decision.exit_reserve == Decimal("100")
    assert decision.soft_floor == Decimal("10200.00")
    assert decision.state is RiskState.ACTIVE


def test_losing_day_allowance_never_scales_below_starting_balance():
    decision = _evaluate(
        snapshot=_snapshot(realized="9800", equity="9750"),
        observation=_observation(equity="9850"),
    )

    assert decision.daily_allowance == Decimal("300.00")
    assert decision.daily_floor == Decimal("9450.00")
    assert decision.hard_floor == Decimal("9700")
    assert decision.soft_floor == Decimal("9800")
    assert decision.liquidation_adjusted_equity == Decimal("9810")
    assert decision.state is RiskState.ACTIVE


def test_configured_reserve_is_separate_from_stressed_flatten_cost():
    stressed = _evaluate(
        observation=_observation(equity="9950", cost="180"),
        exit_reserve=Decimal("120"),
    )
    configured = _evaluate(
        observation=_observation(equity="9950", cost="80"),
        exit_reserve=Decimal("150"),
    )

    assert stressed.exit_reserve == Decimal("120")
    assert stressed.liquidation_adjusted_equity == Decimal("9770")
    assert stressed.state is RiskState.LOCKED_TODAY
    assert configured.exit_reserve == Decimal("150")


def test_missing_snapshot_and_stale_observation_block_new_orders():
    missing = evaluate_risk(
        expected_account_id=ACCOUNT,
        now_utc=NOW,
        snapshot=None,
        observation=_observation(),
    )
    boundary = _evaluate(
        observation=_observation(at=NOW - timedelta(seconds=2))
    )
    stale = _evaluate(
        observation=_observation(at=NOW - timedelta(seconds=2, microseconds=1))
    )

    assert missing.order_gate is OrderGate.NO_NEW_ORDERS
    assert missing.reason == "invalid_input:00UTC snapshot missing"
    assert boundary.order_gate is OrderGate.ALLOW_NEW_ORDERS
    assert stale.order_gate is OrderGate.NO_NEW_ORDERS
    assert stale.reason == "invalid_input:equity observation stale"


def test_snapshot_must_be_current_exact_midnight_utc():
    wrong_time = _evaluate(
        snapshot=_snapshot(at=MIDNIGHT + timedelta(seconds=1))
    )
    prior_day = _evaluate(
        snapshot=_snapshot(at=MIDNIGHT - timedelta(days=1))
    )
    non_utc = _evaluate(
        snapshot=_snapshot(
            at=datetime(2026, 7, 23, tzinfo=timezone(timedelta(hours=1)))
        )
    )

    assert wrong_time.order_gate is OrderGate.NO_NEW_ORDERS
    assert prior_day.order_gate is OrderGate.NO_NEW_ORDERS
    assert non_utc.order_gate is OrderGate.NO_NEW_ORDERS


def test_observation_must_not_predate_snapshot():
    decision = _evaluate(
        observation=_observation(at=MIDNIGHT - timedelta(microseconds=1))
    )

    assert decision.order_gate is OrderGate.NO_NEW_ORDERS
    assert decision.reason == (
        "invalid_input:equity observation predates 00UTC snapshot"
    )


def test_account_mismatch_blocks_without_changing_valid_memory():
    memory = RiskMemory(account_id=ACCOUNT, state=RiskState.ACTIVE)
    decision = _evaluate(
        snapshot=_snapshot(account="other"),
        memory=memory,
    )

    assert decision.order_gate is OrderGate.NO_NEW_ORDERS
    assert decision.reason == "invalid_input:account mismatch"
    assert decision.next_memory == memory


def test_nan_infinity_and_non_decimal_inputs_fail_closed():
    nan_equity = _evaluate(observation=_observation(equity="NaN"))
    infinite_cost = _evaluate(observation=_observation(cost="Infinity"))
    nonpositive_balance = _evaluate(observation=_observation(balance="0"))
    float_reserve = _evaluate(exit_reserve=100.0)

    for decision in (
        nan_equity,
        infinite_cost,
        nonpositive_balance,
        float_reserve,
    ):
        assert decision.order_gate is OrderGate.NO_NEW_ORDERS
        assert decision.daily_floor is None


def test_huge_finite_values_fail_closed_without_escaping_decimal_errors():
    huge_balance = _evaluate(snapshot=_snapshot(realized="1E+999999"))
    huge_current_balance = _evaluate(
        observation=_observation(balance="1E+999999")
    )
    huge_equity = _evaluate(observation=_observation(equity="1E+999999"))
    huge_cost = _evaluate(observation=_observation(cost="1E+999999"))

    for decision in (
        huge_balance,
        huge_current_balance,
        huge_equity,
        huge_cost,
    ):
        assert decision.order_gate is OrderGate.NO_NEW_ORDERS
        assert decision.reason.startswith("invalid_input:")
        assert decision.daily_floor is None


def test_risk_math_is_independent_of_callers_decimal_context():
    with localcontext() as caller_context:
        caller_context.prec = 3
        decision = _evaluate(
            snapshot=_snapshot(realized="10500", equity="10400"),
            observation=_observation(equity="10400", cost="125"),
        )

    assert decision.daily_allowance == Decimal("300.00")
    assert decision.daily_floor == Decimal("10100.00")
    assert decision.liquidation_adjusted_equity == Decimal("10275")
    assert decision.order_gate is OrderGate.ALLOW_NEW_ORDERS


def test_daily_lock_survives_restart_and_resets_only_with_next_day_snapshot():
    first = _evaluate(observation=_observation(equity="9800", cost="0"))
    restarted = _evaluate(
        observation=_observation(equity="10000"),
        memory=first.next_memory,
    )

    assert restarted.state is RiskState.LOCKED_TODAY
    assert restarted.reason == "daily_lock_persisted"

    tomorrow = NOW + timedelta(days=1)
    next_day = evaluate_risk(
        expected_account_id=ACCOUNT,
        now_utc=tomorrow,
        snapshot=_snapshot(
            at=MIDNIGHT + timedelta(days=1),
            realized="10000",
            equity="10000",
        ),
        observation=_observation(at=tomorrow, equity="10000"),
        memory=restarted.next_memory,
    )
    assert next_day.state is RiskState.ACTIVE
    assert next_day.order_gate is OrderGate.ALLOW_NEW_ORDERS


def test_account_halt_survives_restart_and_new_day():
    halted = _evaluate(observation=_observation(equity="9700"))
    tomorrow = NOW + timedelta(days=1)
    restarted = evaluate_risk(
        expected_account_id=ACCOUNT,
        now_utc=tomorrow,
        snapshot=_snapshot(at=MIDNIGHT + timedelta(days=1)),
        observation=_observation(at=tomorrow, equity="11000"),
        memory=halted.next_memory,
    )

    assert restarted.state is RiskState.HALT_ACCOUNT
    assert restarted.order_gate is OrderGate.NO_NEW_ORDERS
    assert restarted.reason == "account_halt_persisted"


def test_target_gate_uses_fresh_realized_balance_not_equity():
    equity_only = _evaluate(
        observation=_observation(balance="10850", equity="10950", cost="50")
    )
    realized_target = _evaluate(
        observation=_observation(balance="10900", equity="10950", cost="50")
    )

    assert equity_only.liquidation_adjusted_equity == Decimal("10900")
    assert equity_only.target_reached is False
    assert equity_only.order_gate is OrderGate.ALLOW_NEW_ORDERS
    assert realized_target.realized_balance == Decimal("10900")
    assert realized_target.target_reached is True
    assert realized_target.state is RiskState.ACTIVE
    assert realized_target.order_gate is OrderGate.NO_NEW_ORDERS
    assert realized_target.reason == "target_reached"
    assert realized_target.next_memory.state is RiskState.ACTIVE


def test_soft_risk_lock_takes_priority_over_realized_target():
    decision = _evaluate(
        observation=_observation(balance="10900", equity="9800", cost="0")
    )

    assert decision.target_reached is True
    assert decision.state is RiskState.LOCKED_TODAY
    assert decision.reason == "soft_floor_touch"


def test_post_entry_stressed_equity_must_remain_strictly_above_soft_floor():
    decision = _evaluate(observation=_observation(equity="10000"))

    assert _post(decision, Decimal("9800")) is OrderGate.NO_NEW_ORDERS
    assert _post(decision, Decimal("9800.01")) is OrderGate.ALLOW_NEW_ORDERS
    assert _post(decision, Decimal("NaN")) is OrderGate.NO_NEW_ORDERS
    assert _post(decision, 9900.0) is OrderGate.NO_NEW_ORDERS


def test_post_entry_gate_never_overrides_locked_or_invalid_account_decision():
    locked = _evaluate(observation=_observation(equity="9800", cost="0"))
    mismatch = _evaluate(observation=_observation(account="other"))

    assert _post(locked, Decimal("12000")) is OrderGate.NO_NEW_ORDERS
    assert _post(mismatch, Decimal("12000")) is OrderGate.NO_NEW_ORDERS


def test_post_entry_binds_account_and_fresh_decision_time():
    decision = _evaluate(observation=_observation(equity="10000"))

    assert _post(
        decision,
        Decimal("9900"),
        now=NOW + timedelta(seconds=2),
    ) is OrderGate.ALLOW_NEW_ORDERS
    assert _post(
        decision,
        Decimal("9900"),
        now=NOW + timedelta(seconds=2, microseconds=1),
    ) is OrderGate.NO_NEW_ORDERS
    assert _post(
        decision,
        Decimal("9900"),
        now=NOW - timedelta(microseconds=1),
    ) is OrderGate.NO_NEW_ORDERS
    assert _post(
        decision,
        Decimal("9900"),
        account="other",
    ) is OrderGate.NO_NEW_ORDERS


def test_post_entry_rejects_forged_or_non_finite_decision_fields():
    decision = _evaluate(observation=_observation(equity="10000"))
    forged = (
        replace(decision, soft_floor=Decimal("NaN")),
        replace(decision, exit_reserve=100.0),
        replace(decision, soft_floor=Decimal("9800.01")),
        replace(
            decision,
            next_memory=RiskMemory(account_id="other", state=RiskState.ACTIVE),
        ),
        replace(decision, account_id="other"),
        replace(decision, target_reached=True),
        replace(decision, target_balance=Decimal("12000")),
        replace(decision, target_balance=Decimal("1E+999999")),
        replace(decision, realized_balance=Decimal("Infinity")),
        replace(
            decision,
            daily_floor=Decimal("9600"),
            hard_floor=Decimal("9600"),
            soft_floor=Decimal("9700"),
        ),
        replace(decision, reason="forged"),
    )

    for candidate in forged:
        assert _post(candidate, Decimal("9900")) is OrderGate.NO_NEW_ORDERS


def test_post_entry_recomputes_and_rejects_checker_forged_floor():
    decision = _evaluate(observation=_observation(equity="10000"))
    forged = replace(
        decision,
        daily_allowance=Decimal("1"),
        daily_floor=Decimal("1"),
        hard_floor=Decimal("1"),
        liquidation_adjusted_equity=Decimal("999999"),
        soft_floor=Decimal("101"),
    )

    assert _post(forged, Decimal("9900")) is OrderGate.NO_NEW_ORDERS


def test_post_entry_rejects_tampered_risk_relevant_source_inputs():
    decision = _evaluate(observation=_observation(equity="10000"))
    tampered = (
        replace(decision, day_start_equity=Decimal("20000")),
        replace(decision, observed_equity=Decimal("20000")),
        replace(decision, stressed_flatten_cost=Decimal("0")),
        replace(decision, exit_reserve=Decimal("50")),
        replace(decision, realized_balance=Decimal("10900")),
    )

    for candidate in tampered:
        assert _post(candidate, Decimal("9900")) is OrderGate.NO_NEW_ORDERS


def test_soft_trigger_uses_liquidation_adjusted_equity():
    decision = _evaluate(observation=_observation(equity="9816", cost="16"))

    assert decision.liquidation_adjusted_equity == Decimal("9800")
    assert decision.state is RiskState.LOCKED_TODAY
    assert decision.order_gate is OrderGate.NO_NEW_ORDERS
