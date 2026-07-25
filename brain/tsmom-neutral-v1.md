# tsmom-neutral-v1

[[README|← Brain index]]

## Anagrafica

- **status**: champion
- **created**: 2026-07-04
- **family**: tsmom-neutral

## Tesi

TIME-SERIES momentum sign-based a portafoglio: long ogni asset con ritorno trailing 168h > 0, short se < 0, equal-weight per gamba, ribilancio 24h. A differenza di xsmom (rank RELATIVO, dollar-neutral by-construction) il book puo' diventare net-long/net-short quando i segni concordano: e' la sleeve DIREZIONALE trend che il dollar-neutral puro lascia sul tavolo. P&L backtest onesto: funding cashflow modellato (-W*r/8, book non neutrale = funding non si azzera). NOTA STORICA (backtest_tsmom_hmm.py, 04/07): la candidata Fase 2 era "tsmom regime-gated HMM" — il gate HMM e' stato FALSIFICATO (ogni variante gated peggiora: lb168 gated-BTC Sharpe 0.33 vs ungated 2.02; replica la lezione 25/06 sulle commodity "il veto hmm peggiora in tutti i subset"). Il tsmom LISCIO invece promuove: Sharpe 2.02, DSR 0.71 (n_trials=12), maxDD -26%, corr +0.40 vs xsmom. lb168 e' stabile anche a reb 168h (1.90); lb336 e' param-sensitive (1.06@24h vs 2.32@168h) -> scelto lb168/reb24. Falsificata se: in paper forward il book non batte l'equal-weight B&H risk-adjusted, o il drawdown supera -30% (coda piu' larga di xsmom, e' il prezzo dell'esposizione direzionale).

## Note evoluzione

v1 seed: tsmom sign lb168 reb24. Mutazioni: lookback (96 debole 0.90, 336 instabile), rebalance, vol-target overlay (candidato naturale: DD -26% e' la coda da tagliare). NON rimettere il gate HMM (falsificato 2 volte: 25/06 commodity, 04/07 crypto).

## Performance (paper)

- equity: $9,449.73
- trade chiusi: 223 · win rate: 46%
- PnL totale: $-550.27
- posizioni aperte ora: 133

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| BTC |  |  |  |  | — |
| ETH |  |  |  |  | — |
| HYPE |  |  |  |  | — |
| xyz:XYZ100 |  |  |  |  | — |
| xyz:SKHX |  |  |  |  | — |
| xyz:SNDK |  |  |  |  | — |
| xyz:MU |  |  |  |  | — |
| xyz:SPCX |  |  |  |  | — |
| xyz:DRAM |  |  |  |  | — |
| xyz:SKHY |  |  |  |  | — |
| xyz:CL |  |  |  |  | — |
| xyz:SP500 |  |  |  |  | — |
| xyz:SILVER |  |  |  |  | — |
| SOL |  |  |  |  | — |
| ZEC |  |  |  |  | — |
| xyz:BRENTOIL |  |  |  |  | — |
| xyz:NVDA |  |  |  |  | — |
| xyz:EWY |  |  |  |  | — |
| xyz:CRCL |  |  |  |  | — |
| xyz:SMSN |  |  |  |  | — |
| xyz:AAPL |  |  |  |  | — |
| xyz:GOLD |  |  |  |  | — |
| xyz:INTC |  |  |  |  | — |
| xyz:META |  |  |  |  | — |
| xyz:GOOGL |  |  |  |  | — |
| xyz:MRVL |  |  |  |  | — |
| LIT |  |  |  |  | — |
| xyz:AMD |  |  |  |  | — |
| PUMP |  |  |  |  | — |
| NEAR |  |  |  |  | — |
| ONDO |  |  |  |  | — |
| xyz:NBIS |  |  |  |  | — |
| xyz:MSFT |  |  |  |  | — |
| xyz:AMZN |  |  |  |  | — |
| XRP |  |  |  |  | — |
| xyz:TSLA |  |  |  |  | — |
| xyz:NFLX |  |  |  |  | — |
| KAITO |  |  |  |  | — |
| xyz:CBRS |  |  |  |  | — |
| xyz:IBM |  |  |  |  | — |
| xyz:BABA |  |  |  |  | — |
| xyz:TSM |  |  |  |  | — |
| mkts:USTECH |  |  |  |  | — |
| xyz:NATGAS |  |  |  |  | — |
| xyz:ORCL |  |  |  |  | — |
| xyz:BB |  |  |  |  | — |
| FARTCOIN |  |  |  |  | — |
| xyz:MSTR |  |  |  |  | — |
| kBONK |  |  |  |  | — |
| AAVE |  |  |  |  | — |
| xyz:KIOXIA |  |  |  |  | — |
| xyz:ZHIPU |  |  |  |  | — |
| xyz:HOOD |  |  |  |  | — |
| SUI |  |  |  |  | — |
| xyz:CRWV |  |  |  |  | — |
| xyz:RKLB |  |  |  |  | — |
| WLD |  |  |  |  | — |
| GRAM |  |  |  |  | — |
| UNI |  |  |  |  | — |
| XPL |  |  |  |  | — |
| ENA |  |  |  |  | — |
| xyz:PURRDAT |  |  |  |  | — |
| LINK |  |  |  |  | — |
| VIRTUAL |  |  |  |  | — |
| BNB |  |  |  |  | — |
| XMR |  |  |  |  | — |
| ADA |  |  |  |  | — |
| CRV |  |  |  |  | — |
| AERO |  |  |  |  | — |
| VVV |  |  |  |  | — |
| xyz:ZM |  |  |  |  | — |
| mkts:US500 |  |  |  |  | — |
| xyz:BE |  |  |  |  | — |
| TRX |  |  |  |  | — |
| kPEPE |  |  |  |  | — |
| xyz:PLTR |  |  |  |  | — |
| xyz:LITE |  |  |  |  | — |
| xyz:LLY |  |  |  |  | — |
| ARB |  |  |  |  | — |
| xyz:NOK |  |  |  |  | — |
| TAO |  |  |  |  | — |
| xyz:DELL |  |  |  |  | — |
| DOGE |  |  |  |  | — |
| xyz:COIN |  |  |  |  | — |
| EIGEN |  |  |  |  | — |
| JUP |  |  |  |  | — |
| xyz:JPY |  |  |  |  | — |
| xyz:JP225 |  |  |  |  | — |
| ZRO |  |  |  |  | — |
| LDO |  |  |  |  | — |
| ETHFI |  |  |  |  | — |
| AVAX |  |  |  |  | — |
| xyz:ARM |  |  |  |  | — |
| JTO |  |  |  |  | — |
| xyz:HIMS |  |  |  |  | — |
| xyz:AVGO |  |  |  |  | — |
| xyz:PLATINUM |  |  |  |  | — |
| xyz:COPPER |  |  |  |  | — |
| XLM |  |  |  |  | — |
| xyz:SHAZ |  |  |  |  | — |
| TRUMP |  |  |  |  | — |
| xyz:BOT |  |  |  |  | — |
| xyz:MINIMAX |  |  |  |  | — |
| LTC |  |  |  |  | — |
| xyz:SMH |  |  |  |  | — |
| xyz:WDC |  |  |  |  | — |
| DOT |  |  |  |  | — |
| MON |  |  |  |  | — |
| APT |  |  |  |  | — |
| PAXG |  |  |  |  | — |
| PENGU |  |  |  |  | — |
| INJ |  |  |  |  | — |
| BCH |  |  |  |  | — |
| PENDLE |  |  |  |  | — |
| MORPHO |  |  |  |  | — |
| xyz:EWJ |  |  |  |  | — |
| xyz:QCOM |  |  |  |  | — |
| PYTH |  |  |  |  | — |
| xyz:QNT |  |  |  |  | — |
| MET |  |  |  |  | — |
| PURR |  |  |  |  | — |
| xyz:EBAY |  |  |  |  | — |
| xyz:ASML |  |  |  |  | — |
| WLFI |  |  |  |  | — |
| xyz:GME |  |  |  |  | — |
| xyz:KR200 |  |  |  |  | — |
| xyz:NOW |  |  |  |  | — |
| xyz:STRC |  |  |  |  | — |
| OP |  |  |  |  | — |
| SPX |  |  |  |  | — |
| xyz:RIVN |  |  |  |  | — |
| ASTER |  |  |  |  | — |
| GRASS |  |  |  |  | — |

## Lezioni

- **thesis_right** (basket, —): Promossa a CHAMPION: 40 trade paper, basket_sharpe 1.024, DSR 0.71, win 0.615, PnL 287.57$. Primo champion della famiglia. #lifecycle #promote #paper #champion

## Eventi lifecycle

- **promote** (2026-07-07): 

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
