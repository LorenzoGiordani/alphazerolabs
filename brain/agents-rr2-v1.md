# agents-rr2-v1

[[README|← Brain index]]

## Anagrafica

- **status**: challenger
- **parent**: [[agents-v1]]
- **created**: 2026-06-22

## Tesi

Stesse identiche decisioni del desk agents-v1 (medesimo brief, dibattito, Strategist, Risk Manager — nessuna chiamata LLM aggiuntiva), ma eseguite con RR fisso 2.0 invece del target_r proposto dall'LLM (storicamente ~2.5). A/B puro sullo strato di USCITA: stesse entry, TP piu vicino. Ipotesi di Lorenzo: un TP a 2R viene colpito piu spesso e alza il PnL realizzato. Falsificata se: a parita di entry, RR2 non batte agents-v1 su PnL realizzato e Sharpe-R in paper.

## Note evoluzione

v1 — variante esecuzione RR2 di agents-v1, costo LLM zero (riusa le decisioni).

## Performance (paper)

- equity: $9,892.85
- trade chiusi: 4 · win rate: 25%
- PnL totale: $-106.90
- posizioni aperte ora: 1

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| ZEC | short | 413.94719399999997 | 424.70982104399997 | 392.42193991199997 | $1,776.67 |

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| SOL | stopped | 70.90751716369918 | $-49.53 |
| SUI | stopped | 0.67534547298618 | $-50.64 |
| ZEC | target | 407.37598370496 | $74.52 |
| ETH | stopped | 1578.6414258543402 | $-81.25 |

## Lezioni

- **execution_issue** (SOL, $-49.53): Il record di apertura è vuoto (open: {}): senza entry_px, direzione e tesi originale non è possibile distinguere tesi sbagliata da sfortuna. Le strategie agent-driven devono scrivere atomicamente apertura e metadati (direzione, stop teorico, tesi LLM) nello stesso evento; un close senza open rende ogni post-mortem cieco e rompe il feedback loop di apprendimento. #data-logging #missing-open #SOL #agents-rr2-v1 #stopped #post-mortem-gap
- **execution_issue** (SUI, $-50.64): Su altcoin ad alta beta come SUI, stop calcolati con RR statico (2:1 fisso) vengono erosi dal rumore intraday prima che la direzionalità si materializzi; calibrare la larghezza dello stop sulla volatilità realizzata dell'asset (ATR rolling) anziché su un multiplo RR uniforme — e loggare sempre entry_px e thesis al momento dell'apertura, altrimenti il post-mortem non può distinguere tesi sbagliata da stop mal piazzato. #stop-placement #altcoin-volatility #ATR-sizing #agents-rr2-v1 #missing-open-context
- **thesis_right** (ZEC, $74.52): In regime tsmom=-1 con liq_imbalance=-1 confermato, lo short su altcoin illiquido (ZEC) raggiunge il target R:R 2:1 meccanicamente senza richiedere tesi fondamentale: il regime dominante crea vacuum ribassista sul book sottile sufficiente a completare il move prima del time-stop. Il rischio non è la direzionalità ma il regime-flip improvviso — in assenza di open leg loggato con thesis+invalidation esplicite, il post-mortem non distingue edge ripetibile da fortuna di timing: le strategie a segnale-confluenza devono loggare l'open con la stessa formalità delle strategie LLM. #regime-alignment #tsmom #bear-regime #rr2-mechanical #altcoin-illiquidity #falsifiability
- **thesis_wrong** (ETH, $-81.25): Un segnale di breakdown intraday + volume_surge non è sufficiente per dichiarare una rottura "strutturale": senza conferma multi-timeframe (4H/daily chiusura sotto il livello rotto) la probabilità di false breakdown (V-reversal) rimane elevata. In regime bear, i livelli rotti al ribasso attraggono liquidity grabs che generano proprio i volume_surge che sembrano "conferma". Regola: quando l'unica conferma di continuation è un range break su timeframe inferiore all'1H, richiedere almeno una candela di follow-through chiusa sotto il livello PRIMA di entrare, oppure scalare l'entry in due tranche (50% on-break, 50% su retest del livello rotto come resistance). Questo filtra la maggior parte dei liquidity grabs. #false_breakdown #volume_surge_trap #multi_timeframe_confluence #intraday_breakout_failure #eth #bear_regime_reversal

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
