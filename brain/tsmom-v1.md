# tsmom-v1

[[README|← Brain index]]

## Anagrafica

- **status**: challenger
- **created**: 2026-06-12

## Tesi

Time-series momentum (Moskowitz-Ooi-Pedersen): il segno del ritorno passato predice il ritorno futuro, su ogni asset class — l'edge istituzionale più documentato. Adattato a 1h: concordanza 7g+30g, posizionale con stop largo. Falsificata se: su basket misto crypto+commodities+index non batte buy-and-hold risk-adjusted su 6 mesi.

## Note evoluzione

TSMOM canonico adattato: orizzonti 7g/30g, exit posizionali (10 giorni).

## Performance (paper)

- equity: $9,688.43
- trade chiusi: 3 · win rate: 0%
- PnL totale: $-304.89
- posizioni aperte ora: 3

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| xyz_CL | short | 80.79383555908203 | 84.02558898144531 | 71.09857529199219 | $2,448.34 |
| xyz_BRENTOIL | short | 83.75324264373779 | 87.1033723494873 | 73.70285352648926 | $2,448.06 |
| xyz_SILVER | short | 71.09078235626221 | 73.9344136505127 | 62.559888473510746 | $2,422.38 |

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| BTC | stopped | 65589.15737643359 | $-101.64 |
| ETH | stopped | 1727.6583308936642 | $-101.63 |
| xyz_GOLD | stopped | 4373.615723492864 | $-101.62 |

## Lezioni

- **thesis_right** (basket, —): TSMOM (7g+30g concordi, exit posizionali) conferma la letteratura: Sharpe medio 1.69, 8/9 asset positivi su basket misto. I segnali universali OHLCV viaggiano cross-asset; funding/flow restano additivi solo su crypto. Nota: consistenza per fold bassa (25/54) - tipico del trend following, guadagna a strappi nei trend e resta piatto nel chop. #tsmom #trend-following #cross-asset #conferma
- **thesis_wrong** (BTC, $-101.64): Un segnale TSMOM short su BTC dopo un drawdown multi-giorno tende a coincidere con l'esaurimento del momentum ribassista, non con la sua accelerazione. Prima di entrare short su TSMOM in contesti di alta volatilità, esigere conferma strutturale (es. incapacità di rimbalzo su daily close o break di supporto volumetrico) per distinguere trend in atto da momentum già consumato. #tsmom #momentum_exhaustion #BTC #short #whipsaw #entry_timing
- **thesis_wrong** (ETH, $-101.63): Il segnale tsmom -1 era tecnicamente valido sul passato ma il momentum aveva già esaurito la direzionalità: ETH a 1660 era vicino all'estremo del drawdown recente e il prezzo ha immediatamente invertito. Un filtro di 'freshness' (il segnale -1 deve essere presente da ≤2 barre, non cronico) e la conferma cross-sectional (ETH sotto-performante rispetto al basket nella stessa finestra) separano i momentum genuini dai falsi segnali in regime di possibile mean-reversion. #tsmom #signal_staleness #trend_exhaustion #whipsaw #regime_filter
- **thesis_wrong** (xyz_GOLD, $-101.62): Un segnale tsmom=-1 su un asset con forte tailwind macro (oro in regime risk-off / dollaro debole) ha edge vicino a zero: il momentum di breve periodo è rumore rispetto al flusso dominante. I segnali tsmom short su safe-haven richiedono un filtro regime (es. dollaro in trend rialzista O risk appetite positivo) prima di entrare — senza conferma macro, il fade è contro la corrente più forte. #tsmom #regime_filter #macro_override #gold #short #trend_following #false_signal

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
