# lux-confluence-rr2-v1

[[README|← Brain index]]

## Anagrafica

- **status**: challenger
- **parent**: [[lux-0.1-beta]]
- **created**: 2026-06-22

## Tesi

La confluenza LUX e l'edge piu validato del desk: trend (tsmom) + liquidazioni reali (liq_imbalance) + forecast Kronos concordi = setup top-conviction. Questo challenger prende ESATTAMENTE quella confluenza a 3 gambe ma cambia solo l'uscita: stop ATR-adattivo + RR2 invece del RR del parent. Ipotesi (di Lorenzo): su entry ad alta convinzione un TP a 2R viene colpito molto piu spesso di RR alti, alzando il PnL realizzato senza degradare il rischio. Cambio SOLO su exit → zero rischio extra sull'entry, gia validato. Falsificata se: a parita di entry, RR2 non batte il parent (lux-0.1-beta) su Sharpe e PnL realizzato in walk-forward + paper.

## Note evoluzione

v1 — confluenza LUX 3-gambe (parent lux-0.1-beta) con exit RR2 + stop ATR3. Test mirato dell'ipotesi RR2 di Lorenzo sull'edge validato. Basket 9-asset 6m: meanSharpe 1.47, +14.66%, 8/9 positivi, worstDD -13.8% → batte i parent (tsmom-atr 1.26, lux-0.1-beta 0.65). Ipotesi RR2 confermata in backtest; il paper e il gate finale. Mutazioni: RR, stop_atr_mult, soglie delle gambe.

## Performance (paper)

- equity: $10,926.10
- trade chiusi: 6 · win rate: 50%
- PnL totale: $283.59
- posizioni aperte ora: 6

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| ZEC | short | 398.640256 | 422.63974085714284 | 350.64128628571433 | $1,769.81 |
| CRV | short | 0.1884623 | 0.19979788957142855 | 0.16579112085714287 | $1,804.45 |
| XRP | short | 1.03239348 | 1.0717284685714286 | 0.9537235028571431 | $2,868.76 |
| SOL | short | 67.7184536 | 71.82099007142857 | 59.513380657142854 | $1,803.98 |
| ETH | short | 1554.48904 | 1615.0769199999997 | 1433.31328 | $2,803.79 |
| NEAR | short | 1.81233746 | 1.935377132857143 | 1.5662581142857142 | $1,609.49 |

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| ETH | stopped | 1721.735645416286 | $-102.74 |
| ZEC | stopped | 441.587125193657 | $-101.55 |
| WLD | stopped | 0.5931814048441715 | $-100.95 |
| ETH | target | 1645.642791317143 | $192.77 |
| CRV | target | 0.19822570635668574 | $197.56 |
| NEAR | target | 1.938799922448 | $198.50 |

## Lezioni

- **execution_issue** (ETH, $-102.74): Quando tsmom è negativo (-1) su un long, il segnale di momentum deve essere un veto strutturale, non un voto minoritario: al momento dell'apertura tsmom=-1 contraddiceva la direzione mentre liq_imbalance e kronos_forecast votavano 2:1. La tesi dichiarava AND logico ma il sistema ha eseguito come majority-vote, rimuovendo il filtro più persistente (momentum batte lead signals su orizzonti intraday). Imporre tsmom come veto-gate elimina i long con momentum strutturalmente avverso. #tsmom_veto #signal_aggregation_error #momentum_persistence #entry_filter #confluence_logic
- **execution_issue** (ZEC, $-101.55): In strategie AND-confluence, un segnale componente negativo è un veto assoluto: tsmom=-1 a open vietava il long indipendentemente dagli altri due segnali. Entrare con 2/3 del consenso trasforma un AND-gate in un majority-vote non dichiarato — abbassa la soglia e invalida il backtest della strategia. Regola generale: se anche un solo segnale richiesto dalla tesi è contro-direzionale all'ingresso, la trade non esiste. #and-gate-violation #signal-confluence #tsmom-veto #execution #crypto-momentum
- **thesis_wrong** (WLD, $-100.95): I segnali di confluenza tecnica su altcoin ad alta beta (WLD, SUI, etc.) devono essere filtrati dal regime direzionale del basket macro: se tsmom/lux-0.1-beta sparano short su BTC/ETH/SOL/NEAR nello stesso momento, qualsiasi long su altcoin speculativo è un fade del regime, non una confluence reale — i segnali tecnici sparano comunque perché non vedono il contesto cross-asset. Prerequisito per long altcoin: almeno BTC e ETH devono essere flat o long nel basket. #regime-mismatch #altcoin-long #confluence-false-signal #bear-market-filter #cross-asset-regime #lux-confluence-rr2-v1
- **thesis_right** (ETH, $192.77): In un vote di confluenza 2/1 dove il segnale forecast diverge da momentum e flow (come kronos=+1 contro tsmom=-1 e liq_imbalance=-1), il move direzionale tende a essere rapido e poco esteso: impostare tp1 al 50% entry-target permette di garantire profitto prima che il segnale forecast leading si materializzi in inversione. #confluence_vote #signal_divergence #partial_take_profit #forecast_vs_flow #short
- **thesis_right** (CRV, $197.56): Strategie confluence con RR≥2 su token DeFi mid-cap funzionano meglio quando più segnali si allineano prima dell'entry: il target statico 2:1 cattura il movimento medio senza inseguire l'upside, e la chiusura disciplinata al target evita il rischio di mean-reversion su asset illiquidi come CRV. Mantenere il target fisso — non alzarlo in corsa — è il vantaggio strutturale di questo setup. #confluence #defi #target_hit #rr2 #discipline
- **thesis_right** (NEAR, $198.50): Quando tsmom e kronos_forecast convergono short con liq_imbalance come conferma secondaria, il segnale di confluence ha sufficiente edge per tenere la posizione fino al target pieno senza uscite parziali anticipate: RR2 è giustificato e va rispettato. #confluence #tsmom #short #target_hit #rr2

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
