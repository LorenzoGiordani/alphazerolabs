# lux-flow-confluence/lux-nw-liq/lux-confluence-rr2

[[README|← Brain index]]

## Anagrafica

- **status**: live
- _nessuno spec YAML: pagina da dati runtime_

## Performance (paper)

- equity: —
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 0

## Lezioni

- **thesis_wrong** (basket, —): Tutte le strategie per-simbolo erano rumore colorato: Sharpe 0.12-0.71 / DSR 0.40-0.87 vs xsmom-port 2.11. Il loop per-simbolo e' stato SVUOTATO il 26/06 (lux-flow-confluence, lux-nw-liq, lux-confluence-rr2 ritirate). L'edge reale abita l'engine portfolio (dollar-neutral, spread mantenuto), non i trade discreti stop-based. Lezione capitale: quando un segnale ha IC debole per-simbolo ma forte come book (xsmom: IC +0.028 → Sharpe 2.11), la ricerca di edge simili per-simbolo e' fuorviante; va cercato nei portfolio factors. Il progetto e' ora tutto engine:portfolio (xsmom core + multihorizon conservative). #lifecycle #retire #per_symbol #portfolio #honest_audit

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
