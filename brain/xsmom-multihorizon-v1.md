# xsmom-multihorizon-v1

[[README|← Brain index]]

## Anagrafica

- **status**: challenger
- **parent**: [[xsmom-port-v1]]
- **created**: 2026-06-26

## Tesi

CROSS-SECTIONAL MOMENTUM MULTI-ORIZZONTE. Stesso edge del parent xsmom-port-v1 (rank relativo nel basket, dollar-neutral) ma mediato su 3 orizzonti (lb 96/168/336h): il segnale a 96h cattura i movimenti di medio termine, 168h e' il core del parent, 336h il trend di fondo. La media dei pesi normalizzati DIVERSIFICA il timing: ogni orizzonte fa entrare/uscire in momenti leggermente diversi → turn-over piu' alto ma drawdown MINORE (correlazione intra-orizzonti < 1). Backtest basket 9 crypto, 12m (26/06): Sharpe 1.85 (vs parent 2.11), ritorno +52% (vs +80%) MA maxDD -15.9% (vs -19.4%, il PIU' BASSO di tutti i test portfolio). Compagno ideale del parent nel book: stesso edge, profilo rischio piu' piano. Falsificata se: in paper il drawdown non risulta inferiore al parent, o se lo Sharpe degrada sotto 1.0 (l'edge si diluisce troppo mediando orizzonti).

## Note evoluzione

v1 seed: media di 3 orizzonti (lb 96+168+336). Mutazioni: aggiunta/rimozione orizzonti, peso non-uniforme (es. 50% core 168h + 25% gli altri), gross.

## Performance (paper)

- equity: $10,248.13
- trade chiusi: 78 · win rate: 60%
- PnL totale: $248.13
- posizioni aperte ora: 6

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| BTC |  |  |  |  | — |
| SOL |  |  |  |  | — |
| SUI |  |  |  |  | — |
| NEAR |  |  |  |  | — |
| WLD |  |  |  |  | — |
| CRV |  |  |  |  | — |

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
