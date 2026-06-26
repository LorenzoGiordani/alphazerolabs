# xsmom-port-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **parent**: [[xsmom-v1]]
- **created**: 2026-06-22
- **family**: xsmom-port

## Tesi

Cross-sectional momentum a PORTAFOGLIO: long il top-terzile del basket per forza relativa (ultime 168h), short il bottom-terzile, dollar-neutral, ribilanciato ogni 168h. Lo stesso edge che da -14.5% nell'engine per-simbolo stop-based (l'IC e troppo sottile per trade discreti) rende +29.4% Sharpe 1.97 maxDD -12% a portafoglio (backtest_portfolio.py, basket 9 crypto 6m): l'edge sta nello SPREAD mantenuto, non nel singolo trade, e il dollar-neutral netta il beta comune (corr basket 0.63) abbattendo il drawdown. Turnover basso (25 ribilanci/6m). Falsificata se: in paper il book dollar-neutral non batte l'equal-weight B&H risk-adjusted, o se l'edge sparisce coi costi reali di ribilanciamento.

## Note evoluzione

v1 — primo engine:portfolio. Cross-sectional momentum dollar-neutral settimanale, gross 1.0. Backtest: +29.4%/Sharpe 1.97/maxDD -12% vs B&H -19.9%/-0.36. Mutazioni: lookback, rebalance_h, quantili, gross, vol-weight.

## Performance (paper)

- equity: $9,902.42
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 4

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| XRP |  |  |  |  | — |
| NEAR |  |  |  |  | — |
| WLD |  |  |  |  | — |
| ZEC |  |  |  |  | — |

## Lezioni

- **thesis_wrong** (basket, —): xsmom-port ritirata manualmente 25/06: l'edge cross-sectional momentum e reale (IC positivo significativo) e in backtest il book dollar-neutral faceva +29% vs -20% benchmark, ma in paper trading non ha prodotto trade chiusi (ribilanciamenti continui, niente chiusure per-simbolo). L'engine portfolio e concettualmente giusto ma richiede piu tuning/osservazione. Registro: riprendere l'engine a portafoglio quando il focus torna sul cross-sectional, con book live piu lungo. #lifecycle #retire #manual #portfolio #cross-sectional

## Eventi lifecycle

- **retire** (2026-06-25): manuale: engine portfolio, 0 trade chiusi in paper. Edge cross-sectional (IC +0.028, t+4.2) reale ma non catturato dal book in fase di tuning

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
