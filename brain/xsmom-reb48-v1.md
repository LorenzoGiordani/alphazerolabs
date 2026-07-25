# xsmom-reb48-v1

[[README|← Brain index]]

## Anagrafica

- **status**: champion
- **parent**: [[xsmom-port-v1]]
- **created**: 2026-07-04
- **family**: xsmom-reb48

## Tesi

Cross-sectional momentum lb168 IDENTICO a xsmom-port-v1 ma ribilanciato ogni 48h invece di 168h. Motivazione dall'OOS split (robustness_portfolio.py, 04/07, train 8m / test 4m mai visti): il config canonico lb168/reb168 crolla OOS (Sharpe 4.18 train -> 0.88 test) mentre lb168/reb48 GENERALIZZA (3.95 train -> 2.37 test, maxDD test -12.8%). Full-period: Sharpe 3.75 vs 3.67, maxDD -11.3% vs -11.9%. Ipotesi: col momentum che rallenta (fold Sharpe 6.49 -> 4.59 -> 1.35 -> 2.28 nel 2026) la cadenza piu' fitta esce prima dalle gambe morte. Challenger A/B contro il parent: stesso segnale, solo il timing cambia — il paper forward decide quale cadenza tenere. Falsificata se: in paper non batte xsmom-port-v1 risk-adjusted su >=8 settimane (allora il vantaggio OOS era rumore del singolo split).

## Note evoluzione

Variante di cadenza del core. Mutazioni sensate: reb 24-72h. Il turnover ~3.5x del parent e' il costo da battere: se il paper mostra fee-drag superiore al vantaggio di timing, ritirare.

## Performance (paper)

- equity: $9,687.02
- trade chiusi: 247 · win rate: 46%
- PnL totale: $-312.98
- posizioni aperte ora: 86

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| BTC |  |  |  |  | — |
| ETH |  |  |  |  | — |
| xyz:SKHX |  |  |  |  | — |
| HYPE |  |  |  |  | — |
| xyz:SNDK |  |  |  |  | — |
| xyz:MU |  |  |  |  | — |
| xyz:SPCX |  |  |  |  | — |
| xyz:DRAM |  |  |  |  | — |
| xyz:CL |  |  |  |  | — |
| xyz:SP500 |  |  |  |  | — |
| ZEC |  |  |  |  | — |
| xyz:BRENTOIL |  |  |  |  | — |
| xyz:NVDA |  |  |  |  | — |
| xyz:SMSN |  |  |  |  | — |
| xyz:EWY |  |  |  |  | — |
| xyz:INTC |  |  |  |  | — |
| xyz:META |  |  |  |  | — |
| xyz:GOOGL |  |  |  |  | — |
| PUMP |  |  |  |  | — |
| ONDO |  |  |  |  | — |
| xyz:AAPL |  |  |  |  | — |
| NEAR |  |  |  |  | — |
| xyz:MRVL |  |  |  |  | — |
| xyz:AMD |  |  |  |  | — |
| xyz:MSFT |  |  |  |  | — |
| xyz:NBIS |  |  |  |  | — |
| xyz:NFLX |  |  |  |  | — |
| xyz:CBRS |  |  |  |  | — |
| xyz:AMZN |  |  |  |  | — |
| xyz:IBM |  |  |  |  | — |
| xyz:ORCL |  |  |  |  | — |
| XPL |  |  |  |  | — |
| KAITO |  |  |  |  | — |
| xyz:BB |  |  |  |  | — |
| SUI |  |  |  |  | — |
| kBONK |  |  |  |  | — |
| xyz:HOOD |  |  |  |  | — |
| AAVE |  |  |  |  | — |
| UNI |  |  |  |  | — |
| xyz:RKLB |  |  |  |  | — |
| xyz:CRWV |  |  |  |  | — |
| xyz:BABA |  |  |  |  | — |
| WLD |  |  |  |  | — |
| ENA |  |  |  |  | — |
| xyz:KIOXIA |  |  |  |  | — |
| BNB |  |  |  |  | — |
| xyz:ZM |  |  |  |  | — |
| xyz:PURRDAT |  |  |  |  | — |
| VIRTUAL |  |  |  |  | — |
| LINK |  |  |  |  | — |
| kPEPE |  |  |  |  | — |
| XMR |  |  |  |  | — |
| TAO |  |  |  |  | — |
| LDO |  |  |  |  | — |
| ETHFI |  |  |  |  | — |
| CRV |  |  |  |  | — |
| xyz:COPPER |  |  |  |  | — |
| ARB |  |  |  |  | — |
| xyz:LITE |  |  |  |  | — |
| xyz:DELL |  |  |  |  | — |
| xyz:COIN |  |  |  |  | — |
| xyz:PLTR |  |  |  |  | — |
| xyz:JPY |  |  |  |  | — |
| xyz:BE |  |  |  |  | — |
| ZRO |  |  |  |  | — |
| EIGEN |  |  |  |  | — |
| AERO |  |  |  |  | — |
| xyz:ARM |  |  |  |  | — |
| xyz:NOK |  |  |  |  | — |
| JTO |  |  |  |  | — |
| xyz:PLATINUM |  |  |  |  | — |
| xyz:ZHIPU |  |  |  |  | — |
| LTC |  |  |  |  | — |
| PENDLE |  |  |  |  | — |
| xyz:BOT |  |  |  |  | — |
| INJ |  |  |  |  | — |
| xyz:WDC |  |  |  |  | — |
| xyz:SHAZ |  |  |  |  | — |
| xyz:MINIMAX |  |  |  |  | — |
| DOT |  |  |  |  | — |
| xyz:KR200 |  |  |  |  | — |
| PYTH |  |  |  |  | — |
| xyz:QNT |  |  |  |  | — |
| xyz:GME |  |  |  |  | — |
| PURR |  |  |  |  | — |
| xyz:QCOM |  |  |  |  | — |

## Lezioni

- **thesis_right** (basket, —): Promossa a CHAMPION: 20 trade paper, basket_sharpe 0.343, DSR None, win 0.421, PnL 67.7$. Primo champion della famiglia. #lifecycle #promote #paper #champion

## Eventi lifecycle

- **promote** (2026-07-05): 

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
