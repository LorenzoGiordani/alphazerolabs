# funding-carry-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **created**: 2026-07-02

## Tesi

FUNDING-CARRY cross-section (Koijen-style carry). Carry di un long = -funding_rate (su HL funding>0 e' pagato DA long VERSO short). Carry trade: long gli asset ad alto carry (funding piu' negativo), short i basso-carry. Ortogonale al momentum (ranka funding, non rendimento). CRITICO: il carry ha un FLUSSO DI CASSA vero (funding) — il P&L modella ENTRAMBI price moves + cashflow Σ_i(-w_i*r_i). Falsificata se in walk-forward non mantiene Sharpe>1.5 con cassflow reale, o se corr con xsmom >0.4.

## Note evoluzione

RETIRED 02/07 sera. Backtest iniziale (cassflow funding applicata ogni barra oraria invece che per-intervallo 8h) dava Sharpe 2.36/DSR 0.79 -> PROMOSSO: ERA UN BUG, la cassflow era sovrastimata ~8-10x. Dopo fix (rate diviso per 8): Sharpe 1.08, +31.0%, maxDD -21.0%, DSR 0.26, 293 rebal -> DEBOLE, sotto soglia zoo (Sharpe>1 & DSR>=0.5). Contributo REALE del funding harvest ~5-7% in 12m (non ~50%). La strategia collassa nel price-only (Sharpe 0.90) + piccolo harvest. Ortogonalita' a xsmom resta genuina (corr +0.04) ma un fattore ortogonale DEBOLE non costruisce portafoglio. Lezione in [[wiki/Lezioni Apprese e Falsificazioni]]: verifica sempre le unita' del funding (per- intervallo vs orario). Per riaprire: modellare funding correttamente + sweep lookback con cassflow reale, solo se risorge sopra soglia.

## Performance (paper)

- equity: —
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 0

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
