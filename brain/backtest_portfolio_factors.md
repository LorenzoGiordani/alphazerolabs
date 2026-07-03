# backtest_portfolio_factors

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

- **thesis_wrong** (basket, —): Sweep di 8 fattori portfolio ortogonali a xsmom: NESSUNO batte il core. (1) Funding carry book Sharpe 0.39-0.77 — NON esplode a portfolio come xsmom, l'IC -0.024 e' troppo debole anche come book. (2) TSMOM long vol-target Sharpe 1.01 ma maxDD -68% (prende tutto il beta bear). (3) xsmom vol-weighted Sharpe 1.05, PEGGIO dell'equal-weight (l'inverse-vol non aiuta). (4) Combo xsmom+tsmom-long Sharpe 1.80 ma DD -33% (il TSMOM inietta drawdown). Solo xsmom-multihorizon (media 3 orizzonti) ha senso: Sharpe 1.85 con DD -16% (il minore) come compagno di diversificazione, non sostituto. Conclusione: xsmom e' l'unico edge forte del progetto; cercare un secondo edge portfolio con questi dati e' diminishing returns. #portfolio #factors #falsification #funding_carry #tsmom #backtest

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
