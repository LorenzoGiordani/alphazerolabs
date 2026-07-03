# xsmom-port/highvol-port/combo

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

- **thesis_partial** (basket, —): AUDIT DI ROBUSTEZZA dei 3 edge portfolio (parameter stability + block bootstrap + true OOS 8m/4m). Verdetto onesto: NESSUNO passa il gate statistico rigoroso CI95-inf > 1.0, ma NON perche' gli edge sono falsi — perche' 12m (~50 ribilanci settimanali) sono FONDAMENTALMENTE insufficienti per inchiodare uno Sharpe (CI larghi ±2). (1) HIGHVOL e' il piu' affidabile: altopiano largo (100% dei lookback tengono Sharpe>1.5), OOS-freeze Sharpe 3.78, CI [0.37, 4.16]. (2) XSMOM e' reale MA FRAGILE: solo 33% dei lookback vicini tengono, CI [-0.16, 4.37], E la selezione ingenua su train overfitta (il config best-su-train lb240/reb48 Sharpe 3.53 collassa a OOS -0.79) — mai ri-calibrare i parametri su finestre corte; il config scelto lb168/reb168 invece generalizza (OOS 2.29). (3) COMBO 70/30: Sharpe 2.62 CI [0.43, 4.76], OOS 3.05 maxDD -9.6%, e il bootstrap del DD mostra coda avversa 5% a -25.5% con solo 6% di prob di drawdown peggiore di -25% — la diversificazione (corr 0.28) abbassa il DD in modo genuino. TROVATA: il blend ratio sweep mostra che w_xs=0.50 batte leggermente il 70/30 scelto (Sharpe 2.75 vs 2.62, stesso maxDD -15.8%) — altopiano robusto, 50/50 e' il config marginalmente migliore. CAVEAT giallo: l'OOS (ultimi 4m) e' Sharpe PIU' ALTO dell'in-sample — il test window e' breve e probabilmente regime-favorabile (non leggere l'OOS 3.x come attesa realistica). Conclusione capitale: la certezza statistica NON si compra con piu' backtest sugli stessi dati — serve TEMPO (track record forward out-of-sample). Questo conferma che il gate verso M5 (vault on-chain) e' di TEMPO non di codice, esattamente come gia' scritto nel README. Le strategie sono PROMETTENTI ma non ancora PROVATE. #robustness #bootstrap #oos #overfitting #selection_bias #portfolio #honest_audit #dsr

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
