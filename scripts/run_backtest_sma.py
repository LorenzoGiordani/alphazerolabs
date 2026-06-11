"""Step 2 — validazione harness con strategia nota (SMA 20/50 cross, BTC 6 mesi).

Atteso: numeri sensati, non strabilianti. Serve a fidarsi del metro di misura,
non a trovare alpha.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from backtest.engine import Backtest
from backtest.metrics import buy_and_hold, compute, report

FAST, SLOW = 20, 50
MONTHS = 6


def sma_cross(history: pd.DataFrame) -> float:
    if len(history) < SLOW:
        return 0.0
    close = history.close
    fast = close.iloc[-FAST:].mean()
    slow = close.iloc[-SLOW:].mean()
    return 1.0 if fast > slow else -1.0  # long/short 1x, mai flat


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    candles = pd.read_parquet(f"data/candles/{symbol}.parquet")
    candles = candles.tail(MONTHS * 30 * 24).reset_index(drop=True)
    print(f"{symbol}: {len(candles)} candele 1h, {candles.ts.min():%Y-%m-%d} → {candles.ts.max():%Y-%m-%d}\n")

    bt = Backtest(candles)
    equity = bt.run(sma_cross)

    print(report(f"SMA {FAST}/{SLOW} long/short", compute(equity, bt.trades)))
    print(report("Buy & hold 1x", buy_and_hold(candles)))


if __name__ == "__main__":
    main()
