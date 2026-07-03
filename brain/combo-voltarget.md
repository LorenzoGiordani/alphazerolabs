# combo-voltarget

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

- **thesis_right** (basket, —): VOL-TARGET OVERLAY (Moreira-Muir 2017 adattato) riduce la coda DD con costo Sharpe nullo. Scala il gross m = clip(sigma*/sigma_realized, 0.3, 1.5) dove sigma_realized e' la vol annualizzata del BOOK STESSO sui rendimenti passati (rolling 720h, anti-lookahead). Motivo per cui FUNZIONA: la volatilita' clusterizza (GARCH) -> i rendimenti avversi si concentrano nei periodi ad alta vol -> de-riskare in quei periodi abbatte la coda. RISULTATO combo 50/50 sigma*=20% vs baseline (OFF): Sharpe 2.68 vs 2.75 (delta -0.06, nullo), maxDD -11.3% vs -15.8% (-4.5pp), coda5% DD -17.9% vs -23.2% (+5.3pp), P(DD<-25%) 0% vs 3% (rovina eliminata). Gradiente MONOTONO pulito (sigma*=20/25/30% -> coda -17.9/-22/-25.9%) = non e' overfit a un punto fortunato. avg_gross scende a 0.72-0.78 (de-risk ~25% medio), moltiplicatore min 0.34 nei periodi turbolenti. La firma (costo Sharpe minuscolo + riduzione DD materiale nella coda) e' ESATTAMENTE cio' che Moreira-Muir documentano come vol-targeting reale. SWEET SPOT sigma*=20-25%. CAVEAT onesta': sigma*, vol_window, floor/cap sono NUOVI parametri selezionati sui dati (selection bias); ma il risultato e' robusto sull'intervallo [20%,25%] e floor/cap non sono binding (m min 0.34 > floor 0.3, cap mai toccato). DEPLOY: non cablato a caldo nel paper engine (portfolio_paper.py e' stateless, serve storare equity history; il paper track record e' il gate M5, non si rischia senza test dedicati). Candidato pronto: combo 50/50 + sigma*=20% overlay. #vol_target #volatility_managed #moreira_muir #drawdown_reduction #risk_management #garch #portfolio #robustness

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
