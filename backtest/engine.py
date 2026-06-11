"""Exchange simulato per backtest su candele 1h (perps Hyperliquid).

Modello: una posizione per asset, esposizione target ∈ [-max_lev, +max_lev]
come frazione dell'equity. Fill all'open della candela successiva (no lookahead),
fee taker + slippage su ogni variazione, funding orario sulle posizioni aperte,
liquidazione approssimata (prezzo oltre 1/leva dall'entry → equity della posizione
azzerata), stop-loss opzionale per posizione.

Limiti noti (accettati per MVP): funding costante (non storico), slippage fisso
(no impatto da size), niente maintenance margin fine.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

HL_TAKER_FEE = 0.00045          # tier base Hyperliquid
DEFAULT_SLIPPAGE = 0.0002       # 2 bps
DEFAULT_FUNDING_HOURLY = 0.0000125  # ≈0.01%/8h, tipico regime neutro


@dataclass
class Position:
    exposure: float = 0.0   # frazione equity con segno (es. -1.5 = short 1.5x)
    entry_px: float = 0.0
    size_usd: float = 0.0   # nozionale assoluto al momento dell'apertura
    stop_px: float | None = None


@dataclass
class Backtest:
    candles: pd.DataFrame                      # ts, open, high, low, close, volume
    fee: float = HL_TAKER_FEE
    slippage: float = DEFAULT_SLIPPAGE
    funding_hourly: float = DEFAULT_FUNDING_HOURLY
    max_leverage: float = 3.0
    start_equity: float = 10_000.0

    equity_curve: list = field(default_factory=list)
    trades: list = field(default_factory=list)

    def run(self, strategy) -> pd.DataFrame:
        """strategy(history: df ≤ t) -> esposizione target. Ritorna equity curve."""
        df = self.candles.reset_index(drop=True)
        equity = self.start_equity
        pos = Position()

        for i in range(1, len(df)):
            row = df.iloc[i]

            # 1. mark-to-market della posizione sulla candela corrente
            if pos.exposure != 0.0:
                # liquidazione approssimata: move avverso > 1/leva dall'entry
                lev = abs(pos.exposure)
                liq_px = pos.entry_px * (1 - 1 / lev) if pos.exposure > 0 else pos.entry_px * (1 + 1 / lev)
                hit_liq = (row.low <= liq_px) if pos.exposure > 0 else (row.high >= liq_px)
                hit_stop = pos.stop_px is not None and (
                    (row.low <= pos.stop_px) if pos.exposure > 0 else (row.high >= pos.stop_px))

                if hit_liq:
                    equity -= pos.size_usd / lev  # margine della posizione perso
                    self._log_trade(pos, liq_px, row.ts, "liquidated")
                    pos = Position()
                elif hit_stop:
                    px = pos.stop_px * (1 - self.slippage if pos.exposure > 0 else 1 + self.slippage)
                    equity += pos.size_usd * (px / pos.entry_px - 1) * np.sign(pos.exposure)
                    equity -= pos.size_usd * self.fee
                    self._log_trade(pos, px, row.ts, "stopped")
                    pos = Position()
                else:
                    # funding sulle ore di posizione aperta (long paga se rate>0)
                    equity -= pos.size_usd * self.funding_hourly * np.sign(pos.exposure)

            if equity <= 0:
                equity = 0.0
                self.equity_curve.append((row.ts, 0.0))
                break

            # 2. equity mark-to-market per la curva
            mtm = equity
            if pos.exposure != 0.0:
                mtm += pos.size_usd * (row.close / pos.entry_px - 1) * np.sign(pos.exposure)
            self.equity_curve.append((row.ts, mtm))

            # 3. decisione della strategia su dati ≤ t, fill all'open di t+1
            if i + 1 >= len(df):
                break
            target = float(np.clip(strategy(df.iloc[: i + 1]), -self.max_leverage, self.max_leverage))
            if target != pos.exposure:
                next_open = df.iloc[i + 1].open
                # chiudi posizione esistente
                if pos.exposure != 0.0:
                    px = next_open * (1 - self.slippage if pos.exposure > 0 else 1 + self.slippage)
                    equity += pos.size_usd * (px / pos.entry_px - 1) * np.sign(pos.exposure)
                    equity -= pos.size_usd * self.fee
                    self._log_trade(pos, px, df.iloc[i + 1].ts, "closed")
                    pos = Position()
                # apri nuova
                if target != 0.0 and equity > 0:
                    px = next_open * (1 + self.slippage if target > 0 else 1 - self.slippage)
                    size = abs(target) * equity
                    equity -= size * self.fee
                    pos = Position(exposure=target, entry_px=px, size_usd=size)

        return pd.DataFrame(self.equity_curve, columns=["ts", "equity"])

    def _log_trade(self, pos: Position, exit_px: float, ts, reason: str) -> None:
        pnl = pos.size_usd * (exit_px / pos.entry_px - 1) * np.sign(pos.exposure)
        if reason == "liquidated":
            pnl = -pos.size_usd / abs(pos.exposure)
        self.trades.append({
            "ts": ts, "exposure": pos.exposure, "entry_px": pos.entry_px,
            "exit_px": exit_px, "pnl_usd": pnl, "reason": reason})
