"""Pure, fail-closed risk contract for a Propr Turbo 10k challenge.

This module deliberately has no network, filesystem, clock, or order side
effects.  Callers must supply an exact UTC daily snapshot and a fresh equity
observation, then persist the returned ``next_memory`` themselves.

All monetary inputs are required to be :class:`~decimal.Decimal`.  Rejecting
implicit float/string conversion keeps boundary comparisons deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import (
    Clamped,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    FloatOperation,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    Rounded,
    Subnormal,
    Underflow,
    localcontext,
)
from enum import Enum


class RiskState(str, Enum):
    ACTIVE = "ACTIVE"
    LOCKED_TODAY = "LOCKED_TODAY"
    HALT_ACCOUNT = "HALT_ACCOUNT"


class OrderGate(str, Enum):
    ALLOW_NEW_ORDERS = "ALLOW_NEW_ORDERS"
    NO_NEW_ORDERS = "NO_NEW_ORDERS"


@dataclass(frozen=True)
class ChallengeProfile:
    """Challenge constants; ``target_balance`` drives a no-new-entry pass gate."""

    starting_balance: Decimal
    target_balance: Decimal
    static_floor: Decimal
    daily_loss_pct: Decimal


TURBO_10K_PROFILE = ChallengeProfile(
    starting_balance=Decimal("10000"),
    target_balance=Decimal("10900"),
    static_floor=Decimal("9700"),
    daily_loss_pct=Decimal("0.03"),
)


@dataclass(frozen=True)
class DailySnapshot:
    """Frozen 00:00 UTC values for one trading day."""

    account_id: str
    as_of_utc: datetime
    day_start_realized_balance: Decimal
    day_start_equity: Decimal


@dataclass(frozen=True)
class EquityObservation:
    account_id: str
    observed_at_utc: datetime
    realized_balance: Decimal
    equity: Decimal
    stressed_flatten_cost: Decimal


@dataclass(frozen=True)
class RiskMemory:
    """Minimal state a caller must persist across process restarts."""

    account_id: str | None = None
    state: RiskState = RiskState.ACTIVE
    locked_utc_date: date | None = None


@dataclass(frozen=True)
class RiskDecision:
    account_id: str | None
    evaluated_at_utc: datetime | None
    state: RiskState
    order_gate: OrderGate
    reason: str
    target_reached: bool
    target_balance: Decimal | None
    realized_balance: Decimal | None
    day_start_realized_balance: Decimal | None
    day_start_equity: Decimal | None
    observed_equity: Decimal | None
    stressed_flatten_cost: Decimal | None
    liquidation_adjusted_equity: Decimal | None
    daily_allowance: Decimal | None
    daily_floor: Decimal | None
    hard_floor: Decimal | None
    exit_reserve: Decimal | None
    soft_floor: Decimal | None
    next_memory: RiskMemory


class _InvalidRiskInput(ValueError):
    pass


_RISK_CONTEXT = Context(
    prec=34,
    rounding=ROUND_HALF_EVEN,
    Emin=-18,
    Emax=18,
)
for _signal in (
    Clamped,
    DivisionByZero,
    FloatOperation,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    Subnormal,
    Underflow,
):
    _RISK_CONTEXT.traps[_signal] = True


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise _InvalidRiskInput(f"{field} must be Decimal")
    if not value.is_finite():
        raise _InvalidRiskInput(f"{field} must be finite")
    try:
        with localcontext(_RISK_CONTEXT) as context:
            checked = context.create_decimal(value)
    except DecimalException as exc:
        raise _InvalidRiskInput(f"{field} outside deterministic Decimal domain") from exc
    if checked != value:
        raise _InvalidRiskInput(f"{field} loses precision in deterministic Decimal domain")
    return checked


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise _InvalidRiskInput(f"{field} must be datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise _InvalidRiskInput(f"{field} must be UTC")
    return value.astimezone(timezone.utc)


def _validated_profile(profile: ChallengeProfile) -> ChallengeProfile:
    starting = _decimal(profile.starting_balance, "starting_balance")
    target = _decimal(profile.target_balance, "target_balance")
    static_floor = _decimal(profile.static_floor, "static_floor")
    daily_pct = _decimal(profile.daily_loss_pct, "daily_loss_pct")
    if starting <= 0:
        raise _InvalidRiskInput("starting_balance must be positive")
    if target <= starting:
        raise _InvalidRiskInput("target_balance must exceed starting_balance")
    if static_floor <= 0 or static_floor >= starting:
        raise _InvalidRiskInput("static_floor must be between zero and starting_balance")
    if daily_pct <= 0 or daily_pct >= 1:
        raise _InvalidRiskInput("daily_loss_pct must be between zero and one")
    return profile


def _valid_memory(memory: object) -> RiskMemory:
    if not isinstance(memory, RiskMemory):
        raise _InvalidRiskInput("memory must be RiskMemory")
    if not isinstance(memory.state, RiskState):
        raise _InvalidRiskInput("memory state invalid")
    if memory.state is RiskState.LOCKED_TODAY and memory.locked_utc_date is None:
        raise _InvalidRiskInput("locked memory missing locked_utc_date")
    if memory.state is not RiskState.LOCKED_TODAY and memory.locked_utc_date is not None:
        raise _InvalidRiskInput("locked_utc_date present outside LOCKED_TODAY")
    if memory.account_id is not None and not memory.account_id.strip():
        raise _InvalidRiskInput("memory account_id empty")
    return memory


def _blocked_for_invalid(memory: object, reason: str) -> RiskDecision:
    if isinstance(memory, RiskMemory) and isinstance(memory.state, RiskState):
        preserved = memory
        state = memory.state
    else:
        preserved = RiskMemory(state=RiskState.HALT_ACCOUNT)
        state = RiskState.HALT_ACCOUNT
    return RiskDecision(
        account_id=None,
        evaluated_at_utc=None,
        state=state,
        order_gate=OrderGate.NO_NEW_ORDERS,
        reason=f"invalid_input:{reason}",
        target_reached=False,
        target_balance=None,
        realized_balance=None,
        day_start_realized_balance=None,
        day_start_equity=None,
        observed_equity=None,
        stressed_flatten_cost=None,
        liquidation_adjusted_equity=None,
        daily_allowance=None,
        daily_floor=None,
        hard_floor=None,
        exit_reserve=None,
        soft_floor=None,
        next_memory=preserved,
    )


def _risk_arithmetic(
    profile: ChallengeProfile,
    day_start_equity: Decimal,
    equity: Decimal,
    flatten_cost: Decimal,
    reserve: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    try:
        with localcontext(_RISK_CONTEXT):
            # The current Propr rulebook body and changelog conflict on whether
            # banked profit expands this allowance. The fixed starting-balance
            # interpretation is stricter, so the live guard deliberately uses it.
            daily_allowance = profile.daily_loss_pct * profile.starting_balance
            daily_floor = day_start_equity - daily_allowance
            hard_floor = max(profile.static_floor, daily_floor)
            liquidation_adjusted_equity = equity - flatten_cost
            soft_floor = hard_floor + reserve
    except DecimalException as exc:
        raise _InvalidRiskInput("risk arithmetic outside deterministic Decimal domain") from exc
    values = (
        daily_allowance,
        daily_floor,
        hard_floor,
        liquidation_adjusted_equity,
        soft_floor,
    )
    for field, value in zip(
        (
            "daily_allowance",
            "daily_floor",
            "hard_floor",
            "liquidation_adjusted_equity",
            "soft_floor",
        ),
        values,
        strict=True,
    ):
        _decimal(value, field)
    return values


def _decision(
    *,
    account_id: str,
    evaluated_at_utc: datetime,
    state: RiskState,
    order_gate: OrderGate,
    reason: str,
    target_reached: bool,
    target_balance: Decimal,
    realized_balance: Decimal,
    day_start_realized_balance: Decimal,
    day_start_equity: Decimal,
    observed_equity: Decimal,
    stressed_flatten_cost: Decimal,
    liquidation_adjusted_equity: Decimal,
    daily_allowance: Decimal,
    daily_floor: Decimal,
    hard_floor: Decimal,
    exit_reserve: Decimal,
    soft_floor: Decimal,
    next_memory: RiskMemory,
) -> RiskDecision:
    return RiskDecision(
        account_id=account_id,
        evaluated_at_utc=evaluated_at_utc,
        state=state,
        order_gate=order_gate,
        reason=reason,
        target_reached=target_reached,
        target_balance=target_balance,
        realized_balance=realized_balance,
        day_start_realized_balance=day_start_realized_balance,
        day_start_equity=day_start_equity,
        observed_equity=observed_equity,
        stressed_flatten_cost=stressed_flatten_cost,
        liquidation_adjusted_equity=liquidation_adjusted_equity,
        daily_allowance=daily_allowance,
        daily_floor=daily_floor,
        hard_floor=hard_floor,
        exit_reserve=exit_reserve,
        soft_floor=soft_floor,
        next_memory=next_memory,
    )


def evaluate_risk(
    *,
    expected_account_id: str,
    now_utc: datetime,
    snapshot: DailySnapshot | None,
    observation: EquityObservation | None,
    memory: RiskMemory = RiskMemory(),
    profile: ChallengeProfile = TURBO_10K_PROFILE,
    exit_reserve: Decimal | None = None,
    max_observation_age: timedelta = timedelta(seconds=2),
) -> RiskDecision:
    """Evaluate current account state and the new-order gate.

    The daily allowance is fixed at ``3% * starting balance``.  This deliberately
    chooses the stricter interpretation of Propr's currently inconsistent
    rulebook body/changelog.  The hard floor is the stricter of the static and
    daily floors.
    A raw-equity hard-floor touch halts the account.  The soft trigger compares
    ``equity - stressed_flatten_cost`` against ``hard_floor + exit_reserve`` and
    locks the account through the current UTC day.  Missing, stale, malformed,
    or mismatched data never authorizes a new order.  A fresh realized-balance
    target touch is an informational pass gate that blocks new entries; the
    caller owns target persistence and flatten execution.
    """

    try:
        profile = _validated_profile(profile)
        memory = _valid_memory(memory)
        if not isinstance(expected_account_id, str) or not expected_account_id.strip():
            raise _InvalidRiskInput("expected_account_id missing")
        account_id = expected_account_id.strip()
        now = _utc(now_utc, "now_utc")
        if not isinstance(snapshot, DailySnapshot):
            raise _InvalidRiskInput("00UTC snapshot missing")
        if not isinstance(observation, EquityObservation):
            raise _InvalidRiskInput("equity observation missing")
        if snapshot.account_id != account_id or observation.account_id != account_id:
            raise _InvalidRiskInput("account mismatch")
        if memory.account_id is not None and memory.account_id != account_id:
            raise _InvalidRiskInput("memory account mismatch")

        snapshot_at = _utc(snapshot.as_of_utc, "snapshot.as_of_utc")
        if (
            snapshot_at.date() != now.date()
            or snapshot_at.time() != datetime.min.time()
        ):
            raise _InvalidRiskInput("current 00UTC snapshot missing")

        observed_at = _utc(observation.observed_at_utc, "observation.observed_at_utc")
        if not isinstance(max_observation_age, timedelta) or max_observation_age <= timedelta(0):
            raise _InvalidRiskInput("max_observation_age must be positive")
        if observed_at < snapshot_at:
            raise _InvalidRiskInput("equity observation predates 00UTC snapshot")
        observation_age = now - observed_at
        if observation_age < timedelta(0):
            raise _InvalidRiskInput("equity observation is from the future")
        if observation_age > max_observation_age:
            raise _InvalidRiskInput("equity observation stale")

        day_start_realized_balance = _decimal(
            snapshot.day_start_realized_balance,
            "snapshot.day_start_realized_balance",
        )
        day_start_equity = _decimal(
            snapshot.day_start_equity,
            "snapshot.day_start_equity",
        )
        current_realized_balance = _decimal(
            observation.realized_balance,
            "observation.realized_balance",
        )
        equity = _decimal(observation.equity, "observation.equity")
        flatten_cost = _decimal(
            observation.stressed_flatten_cost,
            "observation.stressed_flatten_cost",
        )
        configured_reserve = (
            Decimal("100")
            if exit_reserve is None
            else _decimal(exit_reserve, "exit_reserve")
        )
        if (
            day_start_realized_balance <= 0
            or day_start_equity <= 0
            or current_realized_balance <= 0
        ):
            raise _InvalidRiskInput("balance and day-start equity must be positive")
        if flatten_cost < 0 or configured_reserve < 0:
            raise _InvalidRiskInput("cost and reserve must be non-negative")

        reserve = configured_reserve
        (
            daily_allowance,
            daily_floor,
            hard_floor,
            liquidation_adjusted_equity,
            soft_floor,
        ) = _risk_arithmetic(
            profile,
            day_start_equity,
            equity,
            flatten_cost,
            reserve,
        )
        today = now.date()
        target_reached = current_realized_balance >= profile.target_balance

        if memory.state is RiskState.HALT_ACCOUNT:
            next_memory = RiskMemory(account_id=account_id, state=RiskState.HALT_ACCOUNT)
            return _decision(
                account_id=account_id,
                evaluated_at_utc=now,
                state=RiskState.HALT_ACCOUNT,
                order_gate=OrderGate.NO_NEW_ORDERS,
                reason="account_halt_persisted",
                target_reached=target_reached,
                target_balance=profile.target_balance,
                realized_balance=current_realized_balance,
                day_start_realized_balance=day_start_realized_balance,
                day_start_equity=day_start_equity,
                observed_equity=equity,
                stressed_flatten_cost=flatten_cost,
                liquidation_adjusted_equity=liquidation_adjusted_equity,
                daily_allowance=daily_allowance,
                daily_floor=daily_floor,
                hard_floor=hard_floor,
                exit_reserve=reserve,
                soft_floor=soft_floor,
                next_memory=next_memory,
            )

        if day_start_equity <= hard_floor:
            next_memory = RiskMemory(account_id=account_id, state=RiskState.HALT_ACCOUNT)
            return _decision(
                account_id=account_id,
                evaluated_at_utc=now,
                state=RiskState.HALT_ACCOUNT,
                order_gate=OrderGate.NO_NEW_ORDERS,
                reason="day_start_hard_floor_touch",
                target_reached=target_reached,
                target_balance=profile.target_balance,
                realized_balance=current_realized_balance,
                day_start_realized_balance=day_start_realized_balance,
                day_start_equity=day_start_equity,
                observed_equity=equity,
                stressed_flatten_cost=flatten_cost,
                liquidation_adjusted_equity=liquidation_adjusted_equity,
                daily_allowance=daily_allowance,
                daily_floor=daily_floor,
                hard_floor=hard_floor,
                exit_reserve=reserve,
                soft_floor=soft_floor,
                next_memory=next_memory,
            )

        if equity <= hard_floor:
            next_memory = RiskMemory(account_id=account_id, state=RiskState.HALT_ACCOUNT)
            return _decision(
                account_id=account_id,
                evaluated_at_utc=now,
                state=RiskState.HALT_ACCOUNT,
                order_gate=OrderGate.NO_NEW_ORDERS,
                reason="hard_floor_touch",
                target_reached=target_reached,
                target_balance=profile.target_balance,
                realized_balance=current_realized_balance,
                day_start_realized_balance=day_start_realized_balance,
                day_start_equity=day_start_equity,
                observed_equity=equity,
                stressed_flatten_cost=flatten_cost,
                liquidation_adjusted_equity=liquidation_adjusted_equity,
                daily_allowance=daily_allowance,
                daily_floor=daily_floor,
                hard_floor=hard_floor,
                exit_reserve=reserve,
                soft_floor=soft_floor,
                next_memory=next_memory,
            )

        if (
            memory.state is RiskState.LOCKED_TODAY
            and memory.locked_utc_date >= today
        ):
            next_memory = RiskMemory(
                account_id=account_id,
                state=RiskState.LOCKED_TODAY,
                locked_utc_date=memory.locked_utc_date,
            )
            return _decision(
                account_id=account_id,
                evaluated_at_utc=now,
                state=RiskState.LOCKED_TODAY,
                order_gate=OrderGate.NO_NEW_ORDERS,
                reason="daily_lock_persisted",
                target_reached=target_reached,
                target_balance=profile.target_balance,
                realized_balance=current_realized_balance,
                day_start_realized_balance=day_start_realized_balance,
                day_start_equity=day_start_equity,
                observed_equity=equity,
                stressed_flatten_cost=flatten_cost,
                liquidation_adjusted_equity=liquidation_adjusted_equity,
                daily_allowance=daily_allowance,
                daily_floor=daily_floor,
                hard_floor=hard_floor,
                exit_reserve=reserve,
                soft_floor=soft_floor,
                next_memory=next_memory,
            )

        if liquidation_adjusted_equity <= soft_floor:
            next_memory = RiskMemory(
                account_id=account_id,
                state=RiskState.LOCKED_TODAY,
                locked_utc_date=today,
            )
            return _decision(
                account_id=account_id,
                evaluated_at_utc=now,
                state=RiskState.LOCKED_TODAY,
                order_gate=OrderGate.NO_NEW_ORDERS,
                reason="soft_floor_touch",
                target_reached=target_reached,
                target_balance=profile.target_balance,
                realized_balance=current_realized_balance,
                day_start_realized_balance=day_start_realized_balance,
                day_start_equity=day_start_equity,
                observed_equity=equity,
                stressed_flatten_cost=flatten_cost,
                liquidation_adjusted_equity=liquidation_adjusted_equity,
                daily_allowance=daily_allowance,
                daily_floor=daily_floor,
                hard_floor=hard_floor,
                exit_reserve=reserve,
                soft_floor=soft_floor,
                next_memory=next_memory,
            )

        if target_reached:
            next_memory = RiskMemory(account_id=account_id, state=RiskState.ACTIVE)
            return _decision(
                account_id=account_id,
                evaluated_at_utc=now,
                state=RiskState.ACTIVE,
                order_gate=OrderGate.NO_NEW_ORDERS,
                reason="target_reached",
                target_reached=True,
                target_balance=profile.target_balance,
                realized_balance=current_realized_balance,
                day_start_realized_balance=day_start_realized_balance,
                day_start_equity=day_start_equity,
                observed_equity=equity,
                stressed_flatten_cost=flatten_cost,
                liquidation_adjusted_equity=liquidation_adjusted_equity,
                daily_allowance=daily_allowance,
                daily_floor=daily_floor,
                hard_floor=hard_floor,
                exit_reserve=reserve,
                soft_floor=soft_floor,
                next_memory=next_memory,
            )

        next_memory = RiskMemory(account_id=account_id, state=RiskState.ACTIVE)
        return _decision(
            account_id=account_id,
            evaluated_at_utc=now,
            state=RiskState.ACTIVE,
            order_gate=OrderGate.ALLOW_NEW_ORDERS,
            reason="risk_budget_available",
            target_reached=False,
            target_balance=profile.target_balance,
            realized_balance=current_realized_balance,
            day_start_realized_balance=day_start_realized_balance,
            day_start_equity=day_start_equity,
            observed_equity=equity,
            stressed_flatten_cost=flatten_cost,
            liquidation_adjusted_equity=liquidation_adjusted_equity,
            daily_allowance=daily_allowance,
            daily_floor=daily_floor,
            hard_floor=hard_floor,
            exit_reserve=reserve,
            soft_floor=soft_floor,
            next_memory=next_memory,
        )
    except (_InvalidRiskInput, AttributeError, DecimalException, TypeError) as exc:
        return _blocked_for_invalid(memory, str(exc))


def evaluate_post_entry(
    decision: RiskDecision,
    post_entry_stressed_equity: Decimal,
    *,
    expected_account_id: str,
    now_utc: datetime,
    max_age: timedelta = timedelta(seconds=2),
) -> OrderGate:
    """Gate a bound, fresh decision and already-adjusted post-entry equity."""

    try:
        if not isinstance(decision, RiskDecision):
            raise _InvalidRiskInput("decision must be RiskDecision")
        if not isinstance(expected_account_id, str) or not expected_account_id.strip():
            raise _InvalidRiskInput("expected_account_id missing")
        account_id = expected_account_id.strip()
        now = _utc(now_utc, "now_utc")
        evaluated_at = _utc(decision.evaluated_at_utc, "decision.evaluated_at_utc")
        if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
            raise _InvalidRiskInput("max_age must be positive")
        age = now - evaluated_at
        if age < timedelta(0) or age > max_age:
            raise _InvalidRiskInput("decision is future-dated or stale")
        if decision.account_id != account_id:
            raise _InvalidRiskInput("decision account mismatch")
        if not isinstance(decision.state, RiskState):
            raise _InvalidRiskInput("decision state invalid")
        if not isinstance(decision.order_gate, OrderGate):
            raise _InvalidRiskInput("decision order gate invalid")
        if not isinstance(decision.reason, str) or not decision.reason:
            raise _InvalidRiskInput("decision reason missing")
        if type(decision.target_reached) is not bool:
            raise _InvalidRiskInput("decision target flag invalid")

        target_balance = _decimal(
            decision.target_balance,
            "decision.target_balance",
        )
        realized_balance = _decimal(
            decision.realized_balance,
            "decision.realized_balance",
        )
        day_start_realized_balance = _decimal(
            decision.day_start_realized_balance,
            "decision.day_start_realized_balance",
        )
        day_start_equity = _decimal(
            decision.day_start_equity,
            "decision.day_start_equity",
        )
        observed_equity = _decimal(
            decision.observed_equity,
            "decision.observed_equity",
        )
        stressed_flatten_cost = _decimal(
            decision.stressed_flatten_cost,
            "decision.stressed_flatten_cost",
        )
        stored_liquidation_adjusted_equity = _decimal(
            decision.liquidation_adjusted_equity,
            "decision.liquidation_adjusted_equity",
        )
        stored_daily_allowance = _decimal(
            decision.daily_allowance,
            "decision.daily_allowance",
        )
        stored_daily_floor = _decimal(
            decision.daily_floor,
            "decision.daily_floor",
        )
        stored_hard_floor = _decimal(
            decision.hard_floor,
            "decision.hard_floor",
        )
        exit_reserve = _decimal(decision.exit_reserve, "decision.exit_reserve")
        stored_soft_floor = _decimal(
            decision.soft_floor,
            "decision.soft_floor",
        )
        if (
            target_balance != TURBO_10K_PROFILE.target_balance
            or realized_balance <= 0
            or day_start_realized_balance <= 0
            or day_start_equity <= 0
            or stressed_flatten_cost < 0
            or exit_reserve < 0
        ):
            raise _InvalidRiskInput("decision risk values outside valid range")

        (
            daily_allowance,
            daily_floor,
            hard_floor,
            liquidation_adjusted_equity,
            soft_floor,
        ) = _risk_arithmetic(
            TURBO_10K_PROFILE,
            day_start_equity,
            observed_equity,
            stressed_flatten_cost,
            exit_reserve,
        )
        if (
            stored_daily_allowance,
            stored_daily_floor,
            stored_hard_floor,
            stored_liquidation_adjusted_equity,
            stored_soft_floor,
        ) != (
            daily_allowance,
            daily_floor,
            hard_floor,
            liquidation_adjusted_equity,
            soft_floor,
        ):
            raise _InvalidRiskInput("decision derived risk values are inconsistent")
        if decision.target_reached != (realized_balance >= target_balance):
            raise _InvalidRiskInput("decision target flag is inconsistent")

        next_memory = _valid_memory(decision.next_memory)
        if (
            next_memory.account_id != account_id
            or next_memory.state is not decision.state
        ):
            raise _InvalidRiskInput("decision memory binding mismatch")
        if (
            decision.state is RiskState.ACTIVE
            and decision.order_gate is OrderGate.ALLOW_NEW_ORDERS
            and (
                decision.reason != "risk_budget_available"
                or day_start_equity <= hard_floor
                or observed_equity <= hard_floor
            )
        ):
            raise _InvalidRiskInput("active decision inputs are inconsistent")

        stressed_equity = _decimal(
            post_entry_stressed_equity,
            "post_entry_stressed_equity",
        )
        if (
            decision.state is not RiskState.ACTIVE
            or decision.order_gate is not OrderGate.ALLOW_NEW_ORDERS
            or decision.target_reached
            or liquidation_adjusted_equity <= soft_floor
        ):
            return OrderGate.NO_NEW_ORDERS
    except (_InvalidRiskInput, AttributeError, DecimalException, TypeError):
        return OrderGate.NO_NEW_ORDERS
    return (
        OrderGate.ALLOW_NEW_ORDERS
        if stressed_equity > soft_floor
        else OrderGate.NO_NEW_ORDERS
    )
