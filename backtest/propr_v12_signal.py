"""Pure frozen V9/V12 CORE12 signal and one-third Turbo target semantics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import (
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    localcontext,
)
from fractions import Fraction
from typing import Mapping, Sequence


CORE_SYMBOLS = (
    "BTC",
    "ETH",
    "HYPE",
    "SOL",
    "ZEC",
    "LIT",
    "XRP",
    "AAVE",
    "NEAR",
    "XMR",
    "WLD",
    "PUMP",
)
# V9/V12 carried these twelve unavailable sleeves explicitly at zero. The live
# contract projects to CORE12, while frozen_24_projection() preserves the exact
# manifest shape for maker/checker verification.
XYZ_SYMBOLS = (
    "xyz:NVDA",
    "xyz:MU",
    "xyz:MSFT",
    "xyz:META",
    "xyz:GOOGL",
    "xyz:CRCL",
    "xyz:AAPL",
    "xyz:INTC",
    "xyz:TSLA",
    "xyz:ORCL",
    "xyz:HOOD",
    "xyz:AMZN",
)
FROZEN_ORDERED_SYMBOLS = CORE_SYMBOLS + XYZ_SYMBOLS
ORDERED_SYMBOLS = CORE_SYMBOLS

MIN_VALID_BARS = 720
XSMOM_CLOSES = 169
HIGHVOL_RETURNS = 72
VT_WINDOW = 720
LOW_QUANTILE = 0.33
HIGH_QUANTILE = 0.66
PANEL_BUDGET = Fraction(1, 2)
SLEEVE_BLEND = Fraction(1, 2)
WEIGHT_CAP = Fraction(1, 10)
GROSS_MAX = PANEL_BUDGET
TURBO_RISK_SCALE = Fraction(1, 3)
LIVE_GROSS_MAX = GROSS_MAX * TURBO_RISK_SCALE
WEIGHT_QUANTUM = Decimal("0.000000000001")
# This exact finite Decimal was frozen by the replay module at the ambient
# 28-digit context before multiplication and a second ROUND_DOWN quantization.
TURBO_RISK_DECIMAL = Decimal("0.3333333333333333333333333333")
DAY_MS = 86_400_000
WEEK_MS = 7 * DAY_MS
MONDAY_UTC_MS = 4 * DAY_MS

_DECIMAL_CONTEXT = Context(
    prec=50,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
)
_TURBO_SCALE_CONTEXT = Context(
    prec=28,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
)
for _signal in (InvalidOperation, DivisionByZero, Overflow):
    _DECIMAL_CONTEXT.traps[_signal] = True
    _TURBO_SCALE_CONTEXT.traps[_signal] = True


def _binary64(value: float, label: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite binary64 float")
    return value


def _xsmom_score(first_price: Decimal, last_price: Decimal) -> float:
    if (
        type(first_price) is not Decimal
        or not first_price.is_finite()
        or first_price <= 0
        or type(last_price) is not Decimal
        or not last_price.is_finite()
        or last_price <= 0
    ):
        raise ValueError("prices must be positive finite Decimals")
    try:
        with localcontext(_DECIMAL_CONTEXT):
            result = float(last_price / first_price - 1)
    except (DecimalException, OverflowError) as error:
        raise ValueError("decimal arithmetic did not produce a finite result") from error
    return _binary64(result, "xsmom score")


def _type7(values: Sequence[float], probability: float) -> float:
    ordered = sorted(_binary64(value, "values[]") for value in values)
    probability = _binary64(probability, "probability")
    if not ordered or not 0.0 <= probability <= 1.0:
        raise ValueError("Type-7 requires values and probability in [0, 1]")
    try:
        h = (len(ordered) - 1) * probability
        index = math.floor(h)
        fraction = h - index
        result = (
            ordered[index]
            if index == len(ordered) - 1
            else ordered[index]
            + fraction * (ordered[index + 1] - ordered[index])
        )
    except (OverflowError, ValueError) as error:
        raise ValueError("numeric result is not finite") from error
    if not math.isfinite(result):
        raise ValueError("numeric result is not finite")
    return result


def _sample_std(values: Sequence[float]) -> float:
    checked = [_binary64(value, "values[]") for value in values]
    if len(checked) < 2:
        raise ValueError("sample standard deviation requires at least two values")
    try:
        mean = math.fsum(checked) / len(checked)
        variance = math.fsum((value - mean) ** 2 for value in checked) / (
            len(checked) - 1
        )
        result = math.sqrt(max(variance, 0.0))
    except (OverflowError, ValueError) as error:
        raise ValueError("numeric result is not finite") from error
    if not math.isfinite(result):
        raise ValueError("numeric result is not finite")
    return result


def validate_universe(ordered_symbols: Sequence[str]) -> None:
    if tuple(ordered_symbols) != CORE_SYMBOLS:
        raise ValueError("ordered universe must equal the frozen CORE12 symbols")


@dataclass(frozen=True)
class SignalBar:
    open_ms: int
    close: Decimal
    volume: Decimal
    trades: int

    def __post_init__(self) -> None:
        if type(self.open_ms) is not int:
            raise ValueError("open_ms must be an exact integer")
        if (
            type(self.close) is not Decimal
            or not self.close.is_finite()
            or self.close <= 0
        ):
            raise ValueError("close must be a positive finite Decimal")
        if (
            type(self.volume) is not Decimal
            or not self.volume.is_finite()
            or self.volume < 0
        ):
            raise ValueError("volume must be a nonnegative finite Decimal")
        if type(self.trades) is not int or self.trades < 0:
            raise ValueError("trades must be a nonnegative exact integer")

    @property
    def signal_valid(self) -> bool:
        return self.trades > 0 and self.volume > 0


@dataclass(frozen=True)
class AssetSignal:
    eligible: bool
    valid_bar_count: int
    xsmom: float | None
    highvol: float | None


def valid_closes_before(
    bars: Sequence[SignalBar], anchor_ms: int
) -> tuple[Decimal, ...]:
    if type(anchor_ms) is not int:
        raise ValueError("anchor_ms must be an exact integer")
    previous: int | None = None
    selected: list[Decimal] = []
    for bar in bars:
        if not isinstance(bar, SignalBar):
            raise ValueError("bars must contain SignalBar values")
        if previous is not None and bar.open_ms <= previous:
            raise ValueError("bars must be strictly ordered with unique timestamps")
        previous = bar.open_ms
        if bar.open_ms >= anchor_ms:
            break
        if bar.signal_valid:
            selected.append(bar.close)
    return tuple(selected)


def asset_signal(bars: Sequence[SignalBar], anchor_ms: int) -> AssetSignal:
    closes = valid_closes_before(bars, anchor_ms)
    if len(closes) < MIN_VALID_BARS:
        return AssetSignal(False, len(closes), None, None)
    try:
        xsmom = _xsmom_score(closes[-XSMOM_CLOSES], closes[-1])
        recent = closes[-(HIGHVOL_RETURNS + 1) :]
        returns = [
            _xsmom_score(first, last)
            for first, last in zip(recent, recent[1:])
        ]
        highvol = _sample_std(returns)
    except ValueError:
        return AssetSignal(False, len(closes), None, None)
    return AssetSignal(True, len(closes), xsmom, highvol)


def _zero_weights() -> dict[str, Fraction]:
    return {symbol: Fraction(0) for symbol in CORE_SYMBOLS}


def sleeve_weights(
    scores: Mapping[str, float | None],
    ordered_panel: Sequence[str] = CORE_SYMBOLS,
) -> dict[str, Fraction]:
    if tuple(ordered_panel) != CORE_SYMBOLS:
        raise ValueError("ordered_panel must equal the frozen CORE12 panel")
    result = _zero_weights()
    finite: list[tuple[str, float]] = []
    for symbol in CORE_SYMBOLS:
        value = scores.get(symbol)
        if value is None:
            continue
        if type(value) is not float or not math.isfinite(value):
            return result
        finite.append((symbol, value))
    if len(finite) < 6:
        return result
    try:
        low = _type7([value for _, value in finite], LOW_QUANTILE)
        high = _type7([value for _, value in finite], HIGH_QUANTILE)
    except ValueError:
        return result
    if low >= high:
        return result
    shorts = [symbol for symbol, value in finite if value <= low]
    longs = [symbol for symbol, value in finite if value >= high]
    if not shorts or not longs or set(shorts) & set(longs):
        return result
    short_weight = -Fraction(1, 2 * len(shorts))
    long_weight = Fraction(1, 2 * len(longs))
    for symbol in shorts:
        result[symbol] = short_weight
    for symbol in longs:
        result[symbol] = long_weight
    return result


def portfolio_weights(signals: Mapping[str, AssetSignal]) -> dict[str, Fraction]:
    if set(signals) != set(CORE_SYMBOLS) or any(
        not isinstance(signals[symbol], AssetSignal) for symbol in CORE_SYMBOLS
    ):
        raise ValueError("signals must exactly cover the frozen CORE12 symbols")
    result = _zero_weights()
    xsmom = sleeve_weights(
        {
            symbol: signals[symbol].xsmom if signals[symbol].eligible else None
            for symbol in CORE_SYMBOLS
        }
    )
    highvol = sleeve_weights(
        {
            symbol: signals[symbol].highvol if signals[symbol].eligible else None
            for symbol in CORE_SYMBOLS
        }
    )
    for symbol in CORE_SYMBOLS:
        result[symbol] = PANEL_BUDGET * SLEEVE_BLEND * (
            xsmom[symbol] + highvol[symbol]
        )
    return result


def cap_no_regross(weights: Mapping[str, Fraction]) -> dict[str, Fraction]:
    if set(weights) != set(CORE_SYMBOLS):
        raise ValueError("weights must exactly cover the frozen CORE12 symbols")
    result: dict[str, Fraction] = {}
    for symbol in CORE_SYMBOLS:
        value = weights[symbol]
        if not isinstance(value, Fraction):
            raise ValueError("weights must be exact Fractions")
        result[symbol] = max(-WEIGHT_CAP, min(WEIGHT_CAP, value))
    return result


def _quantized_weight(value: Fraction) -> Decimal:
    if not isinstance(value, Fraction):
        raise ValueError("weight must be an exact Fraction")
    try:
        with localcontext(_DECIMAL_CONTEXT):
            decimal = Decimal(value.numerator) / Decimal(value.denominator)
            result = decimal.quantize(WEIGHT_QUANTUM, rounding=ROUND_DOWN)
    except (DecimalException, OverflowError) as error:
        raise ValueError("weight quantization failed") from error
    if not result.is_finite():
        raise ValueError("weight quantization failed")
    return result


def scale_frozen_decimal_weights(
    frozen_weights: Mapping[str, Decimal],
) -> dict[str, Decimal]:
    """Apply the exact second V12-Turbo replay quantization to frozen weights."""

    if set(frozen_weights) != set(CORE_SYMBOLS):
        raise ValueError("weights must exactly cover the frozen CORE12 symbols")
    checked: dict[str, Decimal] = {}
    for symbol in CORE_SYMBOLS:
        value = frozen_weights[symbol]
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError("frozen weights must be finite 1e-12 Decimals")
        try:
            with localcontext(_DECIMAL_CONTEXT):
                quantized = value.quantize(WEIGHT_QUANTUM, rounding=ROUND_DOWN)
        except DecimalException as error:
            raise ValueError("frozen weight quantization check failed") from error
        if quantized != value:
            raise ValueError("frozen weights must be finite 1e-12 Decimals")
        if abs(value) > Decimal("0.100000000000"):
            raise ValueError("frozen target exceeds the per-asset cap")
        checked[symbol] = value
    try:
        with localcontext(_DECIMAL_CONTEXT):
            frozen_gross = sum(
                (abs(value) for value in checked.values()),
                Decimal("0"),
            )
    except DecimalException as error:
        raise ValueError("frozen gross calculation failed") from error
    if frozen_gross > Decimal("0.500000000000"):
        raise ValueError("frozen target exceeds the panel gross budget")
    try:
        result: dict[str, Decimal] = {}
        for symbol in CORE_SYMBOLS:
            # The frozen overlay multiplication happened in Python's default
            # 28-digit HALF_EVEN context before the engine's 1e-12 ROUND_DOWN.
            with localcontext(_TURBO_SCALE_CONTEXT):
                scaled = checked[symbol] * TURBO_RISK_DECIMAL
            with localcontext(_DECIMAL_CONTEXT):
                result[symbol] = scaled.quantize(
                    WEIGHT_QUANTUM,
                    rounding=ROUND_DOWN,
                )
    except (DecimalException, OverflowError) as error:
        raise ValueError("Turbo scaling quantization failed") from error
    if any(abs(value) > Decimal("0.033333333333") for value in result.values()):
        raise ValueError("live target exceeds the per-asset cap")
    try:
        with localcontext(_DECIMAL_CONTEXT):
            live_gross = sum(
                (abs(value) for value in result.values()),
                Decimal("0"),
            )
    except DecimalException as error:
        raise ValueError("live gross calculation failed") from error
    if live_gross > Decimal("0.1666666666666666666666666667"):
        raise ValueError("live target exceeds the panel gross budget")
    return result


def apply_turbo_risk_scale(
    frozen_weights: Mapping[str, Fraction],
) -> dict[str, Decimal]:
    if set(frozen_weights) != set(CORE_SYMBOLS):
        raise ValueError("weights must exactly cover the frozen CORE12 symbols")
    for symbol in CORE_SYMBOLS:
        value = frozen_weights[symbol]
        if not isinstance(value, Fraction):
            raise ValueError("weights must be exact Fractions")
        if abs(value) > WEIGHT_CAP:
            raise ValueError("frozen target exceeds the per-asset cap")
    if sum(abs(value) for value in frozen_weights.values()) > GROSS_MAX:
        raise ValueError("frozen target exceeds the panel gross budget")
    first_quantized = {
        symbol: _quantized_weight(frozen_weights[symbol])
        for symbol in CORE_SYMBOLS
    }
    return scale_frozen_decimal_weights(first_quantized)


def frozen_24_projection(
    core_weights: Mapping[str, Decimal],
) -> dict[str, Decimal]:
    """Restore the exact frozen 24-field shape; every XYZ sleeve remains zero."""

    if set(core_weights) != set(CORE_SYMBOLS):
        raise ValueError("core_weights must exactly cover CORE12")
    for value in core_weights.values():
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError("core_weights must be finite Decimals")
        try:
            with localcontext(_DECIMAL_CONTEXT):
                quantized = value.quantize(WEIGHT_QUANTUM, rounding=ROUND_DOWN)
        except DecimalException as error:
            raise ValueError("core_weights quantization check failed") from error
        if quantized != value or abs(value) > Decimal("0.033333333333"):
            raise ValueError("core_weights violate the frozen live cap or quantum")
    try:
        with localcontext(_DECIMAL_CONTEXT):
            live_gross = sum(
                (abs(value) for value in core_weights.values()),
                Decimal("0"),
            )
            zero = Decimal("0").quantize(WEIGHT_QUANTUM)
    except DecimalException as error:
        raise ValueError("core_weights projection calculation failed") from error
    if live_gross > Decimal("0.1666666666666666666666666667"):
        raise ValueError("core_weights exceed the frozen live gross")
    return {
        symbol: core_weights[symbol] if symbol in CORE_SYMBOLS else zero
        for symbol in FROZEN_ORDERED_SYMBOLS
    }


def daily_vt10(shadow_returns: Sequence[float]) -> float:
    if len(shadow_returns) < VT_WINDOW:
        return 0.0
    window = list(shadow_returns[-VT_WINDOW:])
    if any(type(value) is not float or not math.isfinite(value) for value in window):
        return 0.0
    try:
        annualized = _sample_std(window) * math.sqrt(8760.0)
    except ValueError:
        return 0.0
    if not math.isfinite(annualized) or annualized <= 0.0:
        return 0.0
    return min(1.0, 0.10 / annualized)


@dataclass(frozen=True)
class ActualTarget:
    weekly_anchor_ms: int | None
    weights: tuple[Decimal, ...]

    def as_dict(self) -> dict[str, Decimal]:
        return dict(zip(CORE_SYMBOLS, self.weights))


def flat_target() -> ActualTarget:
    with localcontext(_DECIMAL_CONTEXT):
        zero = Decimal("0").quantize(WEIGHT_QUANTUM)
    return ActualTarget(None, (zero,) * len(CORE_SYMBOLS))


def update_actual_target(
    prior: ActualTarget,
    anchor_ms: int,
    raw_weights: Mapping[str, Fraction],
    daily_multiplier: float,
) -> ActualTarget:
    if not isinstance(prior, ActualTarget) or len(prior.weights) != len(CORE_SYMBOLS):
        raise ValueError("prior target is invalid")
    if type(anchor_ms) is not int:
        raise ValueError("anchor_ms must be an exact integer")
    if (anchor_ms - MONDAY_UTC_MS) % WEEK_MS:
        return prior
    if set(raw_weights) != set(CORE_SYMBOLS):
        raise ValueError("raw_weights must exactly cover the frozen CORE12 symbols")
    multiplier = (
        Fraction(Decimal(repr(daily_multiplier)))
        if type(daily_multiplier) is float
        and math.isfinite(daily_multiplier)
        and 0.0 <= daily_multiplier <= 1.0
        else Fraction(0)
    )
    scaled = {
        symbol: raw_weights[symbol] * multiplier for symbol in CORE_SYMBOLS
    }
    frozen_capped = cap_no_regross(scaled)
    live_scaled = apply_turbo_risk_scale(frozen_capped)
    return ActualTarget(
        anchor_ms,
        tuple(live_scaled[symbol] for symbol in CORE_SYMBOLS),
    )
