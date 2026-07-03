# lux-nw-tsmom-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **parent**: [[lux-nw-continuation-v1]]
- **created**: 2026-06-26

## Tesi

CONFLUENCE 2-GAMBE ortogonali, entrambe validate: breakout strutturale kernel (Nadaraya-Watson, IC +0.105 t+5) AND trend grezzo (tsmom, Moskowitz-Ooi-Pedersen). Le due gambe misurano la stessa cosa (continuation) da angoli INDIPENDENTI:
  - NW = il prezzo ha rotto la banda kernel-MAD (espansione strutturale, volatility-adaptive)
  - tsmom = il segno del ritorno 7g+30g è concorde (pendenza, non livello)
Quando entrambe concordano l'entry è top-conviction: il break non è un falso (tsmom conferma il trend sottostante). È il pattern 'confluence entry' di DaviddTech (breakout + trend filter) applicato ai due edge più forti del desk. Falsificata se: la confluence a 2 gambe NON batte NW da solo su Sharpe/DSR in walk-forward → la gamba tsmom è ridondante e va semplificata (parsimonia).

## Note evoluzione

v1 seed: NW + tsmom (confluence continuation). Mutazioni: soglia mult NW, orizzonti tsmom (168/720 ↔ 96/480), aggiunta liq_imbalance come terza gamba (→ eventuale lux-regime-3leg lineage), RR 1.8-2.5.

## Performance (paper)

- equity: —
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 0

## Lezioni

- **thesis_wrong** (basket, —): La confluence funziona SOLO fra gambe ortogonali per costruzione. nadaraya_watson (breakout kernel) e tsmom (segno del ritorno) misurano entrambi la continuation: sono correlate, non ortogonali. Metterle in AND filtra via proprio le entry migliori (Sharpe -0.30 vs NW standalone +0.18 e tsmom+liq +0.71). Regola: combinare il segnale prezzo-struttura con il FLUSSO (liq_imbalance), non con un altro segnale di momentum. vedi lux-nw-liq (competitivo col champion). #confluence #correlation #nadaraya_watson #falsification #backtest

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
