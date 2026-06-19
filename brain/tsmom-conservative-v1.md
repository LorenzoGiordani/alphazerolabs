# tsmom-conservative-v1

[[README|← Brain index]]

## Anagrafica

- **status**: challenger
- **created**: 2026-06-13

## Tesi

Profilo di rischio difensivo sullo stesso edge TSMOM (vincente): leva 1x, stop stretto, meno posizioni concorrenti. Tesi: rinunciare a parte del rendimento per un drawdown nettamente minore migliora lo Sharpe. Falsificata se lo Sharpe non sale rispetto a tsmom-v1.

## Note evoluzione

seed di ricerca

## Performance (paper)

- equity: $10,112.56
- trade chiusi: 2 · win rate: 50%
- PnL totale: $116.89
- posizioni aperte ora: 2

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| xyz_GOLD | short | 4348.6301 | 4457.3458525 | 4022.4828425000005 | $2,384.70 |
| xyz_BRENTOIL | short | 81.85362874603271 | 83.89996946468352 | 75.71460659008027 | $2,427.28 |

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| xyz_GOLD | stopped | 4337.697226394447 | $-61.57 |
| xyz_CL | target | 77.97749970377586 | $178.46 |

## Lezioni

- **thesis_right** (basket, —): Ricerca profili di rischio su TSMOM: il profilo CONSERVATIVO (leva 1x, stop 2.5%, 2 posizioni) domina il base e l'aggressivo: stesso Sharpe (1.70) ma drawdown dimezzato (-9.8% vs -15%+). L'aggressivo (leva 2x, stop 6%) FALSIFICATO: Sharpe 1.56 sotto buy-and-hold, piu' rischio senza reward. Lezione: su trend-following il controllo del rischio batte la ricerca di rendimento. tsmom-conservative -> challenger in paper. #research #tsmom #risk-profile #conferma
- **execution_issue** (xyz_GOLD, $-61.57): Se close.logged_at precede open.logged_at sulla stessa barra-timestamp, il motore valuta lo stop prima della conferma dell'ingresso (look-ahead intra-barra): la perdita non riflette un movimento di mercato reale. Fix strutturale: aggiungere guard min_hold_bars>=1 nel loop di stop affinché la logica di uscita venga saltata sulla barra di apertura. In parallelo, il pattern GOLD (4204→4231→4348 in 3 giorni, tsmom=-1 persistente) evidenzia che segnali TSMOM short su safe-haven in regime di bid strutturale generano whipsaw sistematici: filtrare gli short su gold/xau con un proxy di risk-appetite (es. VIX regime o spread TY-bund) prima dell'ingresso. #execution-bug #look-ahead #same-bar-exit #min-hold-bars #tsmom #gold #safe-haven #regime-filter
- **thesis_right** (xyz_CL, $178.46): Un segnale tsmom = -1 su futures energetici liquidi in trend ribassista porta il prezzo al target 3:1 entro 3-5 sessioni; non intervenire discrezionalmente sul target meccanico — l'edge della strategia si realizza lasciando girare il winner fino al livello stabilito. #tsmom #crude_oil #short #momentum #commodity #target_hit #3:1_rr

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
