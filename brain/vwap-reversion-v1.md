# vwap-reversion-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **created**: 2026-06-12

## Tesi

Estensioni oltre 2 sigma dal VWAP settimanale senza partecipazione anomala tendono a rientrare verso il VWAP (mean reversion da esaurimento). Il filtro volume_surge ASSENTE distingue l'estensione vuota dal breakout reale — qui si fade solo l'estensione, contro la direzione. Falsificata se: win rate ≤50% o il fade viene travolto nei trend (worstDD > 12%).

## Note evoluzione

v1: fade puro dell'estensione VWAP. Variante futura: AND NOT volume_surge quando il registry supporterà la negazione.

## Performance (paper)

- equity: —
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 0

## Lezioni

- **thesis_wrong** (basket, —): Fade dell'estensione VWAP falsificato 7/7 asset (crypto+commodities+stock): le estensioni oltre 2 sigma IN QUESTO regime sono trend, non esaurimenti. Terza falsificazione consecutiva di tesi mean-reversion (dopo scalp-exit e flow-fade): il regime 2026 H1 premia il trend following, punisce il contrarian. #mean-reversion #vwap #regime #falsificazione

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
