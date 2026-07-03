# highvol-port-v1

[[README|← Brain index]]

## Anagrafica

- **status**: challenger
- **created**: 2026-06-26

## Tesi

HIGH-VOL ANOMALY (inverso della classica low-vol anomaly). Nel basket crypto, gli asset PIU' VOLATILI delle ultime 72h sovraperformano i piu' calmi su orizzonti medi. E' ortogonale al momentum: ranka la VOLATILITA' (dev standard dei rendimenti), non il rendimento stesso. Tesi: il risk premium crypto — le alt piccole/volatili pagano un premio per il rischio sistemico (beta al beta) che il dollar-neutral di xsmom NETTA via. Long le gambe volatili (SOL/CRV/ZEC tipicamente), short i blue chip calmi (BTC/ETH) raccoglie quello che xsmom non vede. Edge VALIDATO (backtest_factor_zoo.py, basket 9 crypto 12m, 26/06):
  HIGH-VOL lb72: Sharpe 2.32, +109%, maxDD -22%, DSR 0.87
  correlazione rendimenti vs xsmom: SOLO +0.28 (diversificazione genuina, non
  ridondanza — le varianti xsmom erano corr ~0.9 fra loro).
Attenzione: NON e' low-vol (quella e' anomalia documentata su EQUITY, regime istituzionale). Su crypto retail il segno e' invertito: il risk-seeking premia la volatilita'. Falsificata se: in walk-forward non mantiene Sharpe > 1.5, o se la correlazione con xsmom sale sopra 0.5 (allora e' momentum mascherato).

## Note evoluzione

v1 seed: high-vol lb72. Mutazioni: vol_lookback (72 ottimo dallo sweep), gross, combo con xsmom (vedi xsmom-highvol-combo). Attenzione overfitting: sweep finestra e' selection — il DSR calcolato su 8 trials zoo e' la guardia.

## Performance (paper)

- equity: $9,835.89
- trade chiusi: 157 · win rate: 47%
- PnL totale: $-164.11
- posizioni aperte ora: 6

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| BTC |  |  |  |  | — |
| ETH |  |  |  |  | — |
| XRP |  |  |  |  | — |
| WLD |  |  |  |  | — |
| ZEC |  |  |  |  | — |
| CRV |  |  |  |  | — |

## Lezioni

- **thesis_right** (basket, —): SECONDO EDGE FORTE trovato: HIGH-VOL anomaly. Long gli asset PIU' VOLATILI del basket (alt piccole) / short i piu' calmi (blue chip). Sharpe 2.32, +109%, maxDD -22%, DSR 0.87. CORRELAZIONE +0.28 con xsmom = diversificazione GENUINA (le varianti xsmom erano corr ~0.9 fra loro e non abbassavano il DD). La combo xsmom 70% + highvol 30% fa Sharpe 2.38 con maxDD -16% (il PIU' BASSO del progetto). Tesi: risk premium crypto — le alt volatili pagano un premio per il rischio sistemico che il dollar-neutral di xsmom netta via. METODO: l'ho trovato con un trucco diagnostico nello zoo a 8 fattori. Quasi tutti erano falsificati (reversal Sharpe -2.86, low-vol -1.68, flow -0.71, OI debole, top-trader -0.72). MA i fattori con Sharpe NEGATIVO FORTE sono SEGNALI INVERTITI. LOW-VOL invertito = HIGH-VOL = Sharpe +1.59. In regime trend 2026-H1, l'inversione porta sempre al momentum/risk-premium, mai a un edge mean-reverting nuovo. Lezione: quando uno zoo di fattori da' Sharpe negativi forti, controlla il segno opposto. #highvol #factor_zoo #orthogonal #diversification #risk_premium #discovery

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
