# liqimb-port-v1

[[README|← Brain index]]

## Anagrafica

- **status**: champion
- **created**: 2026-07-04
- **family**: liqimb-port

## Tesi

LIQUIDATION IMBALANCE cross-sectional a portafoglio: per ogni asset lo sbilancio (liq_short - liq_long)/oi medio degli ultimi 7 giorni; long il top-terzile (dove gli SHORT vengono squeezati), short il bottom, dollar-neutral, ribilancio 24h. E' la versione PORTFOLIO del segnale liq_imbalance gia' validato per-simbolo (14/06: primo edge ortogonale robusto, tsmom+liq 1.02 vs 0.60 baseline, generalizza cross-asset a parametri congelati). Direzione FOLLOW, non fade (liq-cascade-reversal: -52%, falsificata 22/06). Backtest (backtest_factor_zoo2.py, 04/07): Sharpe 1.35 @168h / 1.68 @24h, maxDD -13/-14%, ortogonale (corr +0.36 xsmom, +0.24 highvol). DSR 0.07-0.14 SOTTO soglia: la storia Coinalyze e' corta (~7 mesi daily, ~3 mesi 1h) e il multiple-testing (n_trials=16) pesa. Promossa a challenger COMUNQUE perche' l'edge sottostante ha gia' una validazione indipendente per-simbolo e il DD e' il piu' basso dello zoo2 — il paper forward e' esattamente il test che discrimina. Falsificata se: dopo >=8 settimane di paper lo sharpe_r resta sotto il basket B&H o il DD supera -20%.

## Note evoluzione

v1 seed: liqimb 7d reb24. Mutazioni: lookback (3/7/14g), rebalance, combo con xsmom. Dipendenza operativa: data/coinalyze_1h/ dal cron cloud (6h) — se il collector si ferma il run fallisce chiuso (con <3 simboli nessun rebalance e nessun deploy), invece di degradare silenziosamente.

## Performance (paper)

- equity: $9,911.61
- trade chiusi: 388 · win rate: 46%
- PnL totale: $-88.39
- posizioni aperte ora: 6

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| BTC |  |  |  |  | — |
| SOL |  |  |  |  | — |
| SUI |  |  |  |  | — |
| NEAR |  |  |  |  | — |
| WLD |  |  |  |  | — |
| ZEC |  |  |  |  | — |

## Lezioni

- **thesis_right** (basket, —): Promossa a CHAMPION: 40 trade paper, basket_sharpe 0.605, DSR 0.07, win 0.462, PnL 119.73$. Primo champion della famiglia. #lifecycle #promote #paper #champion

## Eventi lifecycle

- **promote** (2026-07-07): 

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
