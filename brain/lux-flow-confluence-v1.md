# lux-flow-confluence-v1

[[README|← Brain index]]

## Anagrafica

- **status**: challenger
- **parent**: [[lux-confluence-rr2-v1]]
- **created**: 2026-06-25

## Tesi

lux-confluence-rr2-v1 usava una confluence a 3 gambe (tsmom + liq_imbalance + kronos_forecast), ma kronos_forecast e' stato FALSIFICATO come segnale direzionale il 14/06 (Sharpe -0.2/-0.3 standalone, dimezza lo Sharpe come gate). La gamba kronos era quindi MORTA ma ancora cablata in AND: bloccava entrate valide e rumoreggiava con forecast senza alpha. Questa strategia la RIMUOVE: confluence a 2 gambe (tsmom + liq_imbalance), entrambe validate e ortogonali — tsmom = edge di prezzo (Moskowitz, 58 futures), liq_imbalance = unico segnale di flusso forzato sopravvissuto a TUTTE le falsificazioni del progetto (funding, OI, news direzionale, mean-reversion: tutti falsificati; liq resta). Backtest basket 9-asset 6m (validazione pre-deploy, 25/06): Rimuovere kronos MIGLIORA ogni metrica — Sharpe +0.25 -> +1.26, DSR 0.58 -> 0.81, 6/9 -> 9/9 simboli positivi, worstDD -35% -> -22%. La gamba morta dragava il parent. Exit RR2 + stop ATR (validati 21-22/06: RR2 su entry ad alta convinzione TP-itta piu' spesso di RR3; ATR-stop anti noise-stop). Falsificata se: in paper non batte il parent lux-confluence-rr2-v1 su PnL realizzato (il kronos poteva avere valore come gate di rischio non testato), O se liq_imbalance perde la cache Coinalyze (degrada a neutro -> nessuna entry).

## Note evoluzione

v1 seed: confluence 2-gambe (tsmom + liq_imbalance), rimuove la gamba kronos del parent falsificata come direzionale. Mutazioni: soglia liq extreme_pct, lookback liq, RR 1.8-2.5, aggiunta di smart_money_ratio come eventuale terza gamba ortogonale (se mostra IC nel research).

## Performance (paper)

- equity: $9,994.60
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 6

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| BTC | short | 59518.094000000005 | 61749.86184285715 | 55054.55831428572 | $2,666.86 |
| XRP | short | 1.03439308 | 1.0755919814285715 | 0.9519952771428574 | $2,510.43 |
| ZEC | short | 401.249734 | 425.0006971428572 | 353.7478077142857 | $1,689.01 |
| ETH | short | 1563.5872200000001 | 1645.7279314285715 | 1399.3057971428573 | $1,902.96 |
| SOL | short | 67.7184536 | 71.82099007142857 | 59.513380657142854 | $1,650.00 |
| CRV | short | 0.19258147600000003 | 0.20479974614285715 | 0.16814493571428576 | $1,575.44 |

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
