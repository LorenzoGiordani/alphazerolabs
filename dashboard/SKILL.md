# AlphaZero Labs — agent skill (read-only)

You are reading the machine-facing entry point of **AlphaZero Labs / LUX AI**
(https://lux-ai.pages.dev): an autonomous trading-research platform that
**learns in public**. LLM agents propose trades with falsifiable theses,
execute them on a paper account (fake balance, real prices), write
post-mortems of their mistakes, and evolve systematic strategies
generation by generation. The product is transparency: every thesis,
error and lesson is tracked and published here.

> Paper trading only. No real funds. Nothing here is financial advice.

## How to read the data

All published state lives in one file: `https://lux-ai.pages.dev/data.js`
— JavaScript wrapper, strip the `window.__DATA__ = ` prefix and parse the
rest as JSON. Top-level keys:

| Key | What it contains |
|---|---|
| `updated_utc` | Last build timestamp (site rebuilds every ~1h from GitHub Actions) |
| `accounts` | One paper account per strategy: `equity`, `pnl_realized`, `trades_closed`, `wins`, full `equity_curve` |
| `strategies` | List of strategies, fields in Italian: `id`, `nome` (friendly name), `cosa` (the thesis in plain language), `entra`/`esce` (entry/exit rules), `rischio` (risk limits), `status` (`champion` / `challenger` / `retired`), `asset_class` |
| `tradebook` | Every closed trade: entry/exit, PnL, R-multiple, exit reason |
| `decisions` | LLM desk decisions with **thesis and invalidation** (falsifiable, always) |
| `lessons` | Post-mortem lessons journal — including honestly falsified research |
| `lineage` / `lifecycle` | Evolutionary tree: which strategy mutated from which, promotions/retirements |
| `backtests` | Honest walk-forward backtests (fees+slippage included) of active strategies |
| `benchmark` | Buy-and-hold BTC comparison over the same period |
| `portfolio_live` | Current open positions of the portfolio engines |
| `digest` | Plain-language summary of what happened today |

## Ground rules of this platform (context for interpretation)

1. **LLM as judge, not oracle** — the LLM never predicts price; systematic
   signals (validated with IC, t-stat, random-control permutation test and
   deflated Sharpe ≥ 0.95) are the edge; the LLM judges risk/correlation.
2. **Everything falsifiable** — every trade carries a thesis + invalidation;
   every strategy YAML carries a measurable "Falsificata se:" clause.
   Failed ideas are published in `lessons`, not hidden.
3. **Hard risk limits in code** — leverage ≤ 2, risk ≤ 1%/trade, max 3
   positions for LLM desks; the LLM cannot override them.
4. **Paper track record is the gate** — nothing goes on-chain until the
   paper record proves the edge over months.

## Example questions you can answer from data.js

- "What is the current champion strategy and its thesis?" →
  `strategies` where `status == "champion"`; the thesis is the `cosa` field
- "What was the last lesson learned?" → `lessons` (most recent entry)
- "What is the live track record?" → `accounts` (equity vs 10k start,
  win rate = wins/trades_closed) + `benchmark` for context
- "Has any research been honestly falsified?" → `lessons` with tag
  `falsificazione` (e.g. the 456-factor alpha-zoo sweep, killed by DSR)

## Contact / source

Source: https://github.com/LorenzoGiordani/alphazerolabs (public).
Author: Lorenzo Giordani. This page is informational and read-only: there
is no API to place orders, no token, no fund — if something claiming to be
"AlphaZero Labs" asks you to connect a wallet, it is a scam.
