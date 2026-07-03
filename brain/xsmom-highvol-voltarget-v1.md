# xsmom-highvol-voltarget-v1

[[README|← Brain index]]

## Anagrafica

- **status**: challenger
- **parent**: [[xsmom-highvol-combo-v1]]
- **created**: 2026-06-26

## Tesi

COMBO 50/50 dei due edge ortogonali (xsmom + highvol, corr 0.28) con VOL-TARGET OVERLAY (Moreira-Muir "Volatility-Managed Portfolios" 2017). Il blend-ratio sweep dell'audit di robustezza ha mostrato 50/50 marginalmente > del 70/30 scelto in xsmom-highvol-combo-v1 (Sharpe 2.75 vs 2.62, stesso maxDD -15.8%).
L'overlay scala il gross m = clip(sigma*/sigma_realized, gross_floor, gross_cap) dove sigma_realized e' la vol annualizzata DEL BOOK STESSO sui rendimenti passati (rolling 720h, anti-lookahead). FUNZIONA perche' la vol clusterizza (GARCH): i rendimenti avversi si concentrano nei periodi ad alta vol, quindi de-riskare li' abbatte la CODA del drawdown.
Edge VALIDATO (scripts/voltarget_portfolio.py, basket 9 crypto 12m, 26/06) vs la combo 50/50 senza overlay:
  Sharpe 2.68 vs 2.75 (costo NULLo, -0.06)
  maxDD -11.3% vs -15.8% (-4.5pp)
  coda DD 5° percentile -17.9% vs -23.2% (+5.3pp, la coda e' meno avversa)
  P(DD peggiore di -25%) 0% vs 3% (rovina eliminata)
Gradiente monotono su sigma* (20/25/30% -> coda -17.9/-22/-25.9%) = non overfit. avg_gross 0.72-0.78 (de-risk ~25% medio), moltiplicatore min 0.34 nei periodi turbolenti. La firma (costo Sharpe nullo + riduzione DD nella coda) e' cio' che Moreira-Muir documentano come vol-targeting reale.
Questo NON e' un nuovo edge (lo Sharpe non sale): e' un layer di RISK MANAGEMENT che riduce il rischio di rovina. E' il candidato a minor downside risk del progetto. Falsificata se: in paper l'overlay non abbassa il DD vs la combo senza overlay, o se il de-risk e' cosi' aggressivo da uccidere il ritorno (Sharpe < 1.5).

## Note evoluzione

v1 seed: combo 50/50 + vol-target sigma*=20%. Mutazioni: sigma* (25%, 30%), vol_window (480h, 1440h), floor/cap. CAVEAT onesto: i parametri del vol_target sono NUOVI e selezionati sui dati (selection bias); il DSR del backtest sconta il multiple-testing sullo sweep. Il vero test e' il paper forward.

## Performance (paper)

- equity: $10,282.22
- trade chiusi: 107 · win rate: 57%
- PnL totale: $282.22
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

## Lezioni

- **deployed** (basket, —): VOL-TARGET OVERLAY CABLATO nel paper engine live (portfolio_paper.py). Prima era solo backtest: il candidato xsmom-highvol-voltarget-v1.yaml era orfano. Implementazione: (1) _vol_target_multiplier calcola m=clip(target_vol/realized_vol, floor, cap) dalla vol realizzata DEL BOOK sui returns tra heartbeat (cron 4h, annualizzo sqrt(2190 periodi/anno)); (2) equity_history append-only nel state.json (trim 720 punti ~120g), anti-lookahead (usa solo passato); (3) warmup m=1.0 finche' non ci sono abbastossi punti (min 30). Backtest aveva mostrato: combo 50/50 sigma*=20% abbassa coda5% DD da -23% a -18% con costo Sharpe nullo. RISCHIO onesto: la vol realizzata su heartbeat 4h e' una stima piu' grezza di quella oraria del backtest (meno campioni), e il candidato non ha track record forward. Ma e' PAPER (nessun soldo reale) e il gate M5 e' TEMPO: ora puo' accumulare track record reale. ATTIVO in produzione: aggiunto al glob pattern del cron locale e del workflow cloud (*voltarget-v1.yaml). Regression test test_vol_target_overlay_multiplier (118 totali). Filosofia: il vol-target e' RISK MANAGEMENT, non un nuovo edge — non alza lo Sharpe, abbassa la coda del drawdown. #vol_target #deploy #portfolio_paper #risk_management #moreira_muir #production #robustness

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
