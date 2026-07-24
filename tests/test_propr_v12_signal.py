import hashlib
import json
import math
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backtest.propr_v12_signal as signal


QUANTIZATION_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "v12_turbo_third_risk_quantization.json"
)
HOUR_MS = 3_600_000
GOLDEN_XSMOM = 0.2
GOLDEN_HIGHVOL = 0.023570226039551587
GOLDEN_SLEEVE = {
    **{symbol: Fraction(-1, 8) for symbol in signal.CORE_SYMBOLS[:4]},
    **{symbol: Fraction(0) for symbol in signal.CORE_SYMBOLS[4:8]},
    **{symbol: Fraction(1, 8) for symbol in signal.CORE_SYMBOLS[8:]},
}
GOLDEN_PORTFOLIO = {
    **{symbol: Fraction(-1, 16) for symbol in signal.CORE_SYMBOLS[:4]},
    **{symbol: Fraction(0) for symbol in signal.CORE_SYMBOLS[4:8]},
    **{symbol: Fraction(1, 16) for symbol in signal.CORE_SYMBOLS[8:]},
}


def _bars(bar_type=signal.SignalBar, count=720):
    return [
        bar_type(
            i * HOUR_MS,
            Decimal("120") if i == count - 1 else Decimal("100"),
            Decimal("1"),
            1,
        )
        for i in range(count)
    ]


def _ranked_signals(asset_type=signal.AssetSignal):
    return {
        symbol: asset_type(True, 720, float(rank), float(rank))
        for rank, symbol in enumerate(signal.CORE_SYMBOLS)
    }


def test_frozen_core_order_and_strict_signal_bar():
    assert signal.CORE_SYMBOLS == (
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
    assert signal.ORDERED_SYMBOLS == signal.CORE_SYMBOLS
    signal.validate_universe(signal.CORE_SYMBOLS)
    with pytest.raises(ValueError, match="CORE12"):
        signal.validate_universe(tuple(reversed(signal.CORE_SYMBOLS)))

    valid = signal.SignalBar(0, Decimal("1"), Decimal("0"), 0)
    assert valid.signal_valid is False
    malformed = (
        (True, Decimal("1"), Decimal("1"), 1),
        (0, 1.0, Decimal("1"), 1),
        (0, Decimal("NaN"), Decimal("1"), 1),
        (0, Decimal("0"), Decimal("1"), 1),
        (0, Decimal("1"), 1.0, 1),
        (0, Decimal("1"), Decimal("Infinity"), 1),
        (0, Decimal("1"), Decimal("-1"), 1),
        (0, Decimal("1"), Decimal("1"), True),
        (0, Decimal("1"), Decimal("1"), -1),
    )
    for values in malformed:
        with pytest.raises(ValueError):
            signal.SignalBar(*values)


def test_golden_asset_signal_uses_169_closes_and_72_returns():
    result = signal.asset_signal(_bars(), 720 * HOUR_MS)

    assert result == signal.AssetSignal(
        True, 720, GOLDEN_XSMOM, GOLDEN_HIGHVOL
    )


def test_history_is_strictly_ordered_valid_and_before_anchor():
    bars = _bars(count=721)
    bars[-2] = signal.SignalBar(
        bars[-2].open_ms, Decimal("120"), Decimal("0"), 1
    )
    result = signal.asset_signal(bars, 720 * HOUR_MS)
    assert result.valid_bar_count == 719
    assert result.eligible is False

    duplicate = _bars(count=2)
    duplicate[1] = signal.SignalBar(
        duplicate[0].open_ms, Decimal("100"), Decimal("1"), 1
    )
    with pytest.raises(ValueError, match="strictly ordered"):
        signal.asset_signal(duplicate, 3 * HOUR_MS)
    with pytest.raises(ValueError, match="SignalBar"):
        signal.asset_signal([object()], HOUR_MS)
    with pytest.raises(ValueError, match="anchor_ms"):
        signal.asset_signal([], True)


def test_insufficient_history_and_nonfinite_inputs_fail_flat():
    assert signal.asset_signal(_bars(count=719), 720 * HOUR_MS) == (
        signal.AssetSignal(False, 719, None, None)
    )
    assert signal.daily_vt10([0.001] * 719) == 0.0
    assert signal.daily_vt10([0.001] * 719 + [math.nan]) == 0.0

    scores = {
        symbol: float(rank) for rank, symbol in enumerate(signal.CORE_SYMBOLS)
    }
    scores[signal.CORE_SYMBOLS[0]] = math.inf
    assert signal.sleeve_weights(scores) == {
        symbol: Fraction(0) for symbol in signal.CORE_SYMBOLS
    }
    assert signal.sleeve_weights(
        {symbol: float(rank) for rank, symbol in enumerate(signal.CORE_SYMBOLS[:5])}
    ) == {symbol: Fraction(0) for symbol in signal.CORE_SYMBOLS}


def test_type7_sleeve_and_separate_fifty_fifty_blend_match_golden():
    ranked = {
        symbol: float(rank) for rank, symbol in enumerate(signal.CORE_SYMBOLS)
    }
    assert signal.sleeve_weights(ranked) == GOLDEN_SLEEVE

    same = signal.portfolio_weights(_ranked_signals())
    assert same == GOLDEN_PORTFOLIO

    reversed_highvol = {
        symbol: signal.AssetSignal(True, 720, float(rank), float(11 - rank))
        for rank, symbol in enumerate(signal.CORE_SYMBOLS)
    }
    assert signal.portfolio_weights(reversed_highvol) == {
        symbol: Fraction(0) for symbol in signal.CORE_SYMBOLS
    }


def test_cap_and_turbo_scale_never_regross():
    raw = {symbol: Fraction(0) for symbol in signal.CORE_SYMBOLS}
    raw["BTC"] = Fraction(1, 2)
    raw["ETH"] = Fraction(-1, 2)

    capped = signal.cap_no_regross(raw)
    assert capped["BTC"] == Fraction(1, 10)
    assert capped["ETH"] == Fraction(-1, 10)
    assert sum(abs(value) for value in capped.values()) == Fraction(1, 5)

    live = signal.apply_turbo_risk_scale(capped)
    assert live["BTC"] == Decimal("0.033333333333")
    assert live["ETH"] == Decimal("-0.033333333333")
    assert sum(abs(value) for value in live.values()) == Decimal("0.066666666666")

    over_budget = {
        symbol: Fraction(1, 10) for symbol in signal.CORE_SYMBOLS
    }
    with pytest.raises(ValueError, match="gross budget"):
        signal.apply_turbo_risk_scale(over_budget)

    over_asset = {symbol: Fraction(0) for symbol in signal.CORE_SYMBOLS}
    over_asset["BTC"] = Fraction(1, 5)
    with pytest.raises(ValueError, match="per-asset cap"):
        signal.apply_turbo_risk_scale(over_asset)


def test_double_round_down_matches_known_replay_mismatch_vector():
    frozen = {
        symbol: Decimal("0").quantize(signal.WEIGHT_QUANTUM)
        for symbol in signal.CORE_SYMBOLS
    }
    frozen["ETH"] = Decimal("-0.019367944704")

    live = signal.scale_frozen_decimal_weights(frozen)

    assert live["ETH"] == Decimal("-0.006455981567")
    assert live["ETH"] != Decimal("-0.006455981568")


def test_weekly_monday_anchor_vt10_and_live_gross_sixth():
    prior = signal.flat_target()
    frozen = signal.portfolio_weights(_ranked_signals())
    monday = signal.MONDAY_UTC_MS

    unchanged = signal.update_actual_target(
        prior, monday + HOUR_MS, {"malformed": Fraction(1)}, math.nan
    )
    assert unchanged is prior

    target = signal.update_actual_target(prior, monday, frozen, 1.0)
    assert target.weekly_anchor_ms == monday
    assert target.as_dict() == signal.apply_turbo_risk_scale(GOLDEN_PORTFOLIO)
    assert sum(abs(value) for value in target.weights) == Decimal(
        "0.166666666664"
    )
    assert signal.LIVE_GROSS_MAX == Fraction(1, 6)
    projection = signal.frozen_24_projection(target.as_dict())
    assert tuple(projection) == signal.FROZEN_ORDERED_SYMBOLS
    assert all(projection[symbol] == Decimal("0E-12") for symbol in signal.XYZ_SYMBOLS)

    returns = [-0.001, 0.001] * 360
    assert signal.daily_vt10(returns) == 1.0
    assert signal.daily_vt10([math.inf] + returns) == 1.0


def test_bad_monday_multiplier_flattens_and_bad_shapes_reject():
    monday = signal.MONDAY_UTC_MS
    frozen = signal.portfolio_weights(_ranked_signals())

    for multiplier in (math.nan, math.inf, -0.1, 1.1, 1):
        target = signal.update_actual_target(
            signal.flat_target(), monday, frozen, multiplier
        )
        assert target == signal.ActualTarget(
            monday, (Decimal("0E-12"),) * len(signal.CORE_SYMBOLS)
        )

    with pytest.raises(ValueError, match="raw_weights"):
        signal.update_actual_target(
            signal.flat_target(), monday, {"BTC": Fraction(0)}, 1.0
        )
    with pytest.raises(ValueError, match="signals"):
        signal.portfolio_weights({})
    bad_fraction = {symbol: Fraction(0) for symbol in signal.CORE_SYMBOLS}
    bad_fraction["BTC"] = 0.0
    with pytest.raises(ValueError, match="Fractions"):
        signal.cap_no_regross(bad_fraction)


def test_all_52_frozen_instructions_match_turbo_manifest_hash():
    fixture = json.loads(QUANTIZATION_FIXTURE.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == 1
    assert fixture["source_v12_instruction_sha256"] == (
        "c3d67df4cadc2f3598ed68ec4499a2c53f6513a42da6013fab4fd6d47553d09a"
    )
    assert len(fixture["rows"]) == 52

    instructions = []
    for row in fixture["rows"]:
        frozen = {
            symbol: Decimal(value)
            for symbol, value in zip(
                signal.CORE_SYMBOLS,
                row["core_weights"],
                strict=True,
            )
        }
        live = signal.scale_frozen_decimal_weights(frozen)
        projection = signal.frozen_24_projection(live)
        instructions.append(
            {
                "created_at": row["created_at"],
                "kind": "WEEKLY_ALPHA",
                "target_weights": [
                    {"symbol": symbol, "weight": str(projection[symbol])}
                    for symbol in signal.FROZEN_ORDERED_SYMBOLS
                ],
            }
        )
    body = (
        json.dumps(
            instructions,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )
    assert hashlib.sha256(body).hexdigest() == (
        "ad265ac6dd420b57abcfd5d4646e48cedbd890f03eab977f93f7bf1ba2d1e54e"
    )
