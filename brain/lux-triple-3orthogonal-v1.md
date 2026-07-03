# lux-triple-3orthogonal-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **parent**: [[lux-flow-confluence-v1]]
- **created**: 2026-06-26

## Tesi

TRIPLA CONFLUENZA su TRE GAMBE ORTOGONALI PER COSTRUZIONE. Il champion lux-flow-confluence (tsmom + liq_imbalance) e' il live edge piu' forte, ma conferma solo due dimensioni: il trend dell'asset (tempo-assoluto) e il flusso forzato (liquidazioni). Manca la TERZA dimensione: la FORZA RELATIVA dell'asset NEL BASKET. Un trend lungo su SOL vale poco se SOL sta sottoperformando tutto il settore; un trend lungo sull'asset che GUIDA il basket ha continuation molto piu' affidabile. xsection_momentum = rank cross-section del ritorno trailing (cache rigenerata a 12m completa il 26/06: prima era stale a 201g, degradando a neutro i primi 5 mesi). Edge come GATE validato il 26/06: condizionato a un'entry champion attiva, il fwd return firmato a 168h del bucket TOP-rank e' +0.032 vs +0.015 del BOT (Δ +0.017, ~2x). Non e' un segnale direzionale (quello era falsificato come per-simbolo thin-edge in xsmom-v1): e' un QUALITY GATE che filtra le entry a massima convinzione. Tre fonti INDIPENDENTI per costruzione (tempo-assoluto x flusso x cross-section): niente ridondanza, a differenza di lux-nw-tsmom (entrambi momentum, correlate). Falsificata se: in walk-forward basket 9-asset non batte il champion su mean Sharpe/DSR. Se xsection non aggiunge valore a parita' delle altre 2 gambe, il champion resta a 2 (piu' parsimonioso).

## Note evoluzione

v1 seed: champion + xsection_momentum (3 gambe ortogonali). Mutazioni: soglia liq extreme_pct, hi/lo pct xsection, RR 1.8-2.5, time_stop. NOTA: la cache xsection va rigenerata quando cambiano i simboli del basket (precompute_xsection.py).

## Performance (paper)

- equity: —
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 0

## Lezioni

- **thesis_wrong** (basket, —): L'edge cross-sectional momentum e' reale (conditional IC: bucket TOP fwd +0.032 vs BOT +0.015 a 168h quando il champion spara) MA NON e' catturabile nel motore per-simbolo. Il DSL esprime 'segnale attivo = !=0', e xsection e' attivo sia per top-rank(+1) sia bottom-rank(-1): un asset in trend rialzista ma relativamente debole passa il gate e viene comprato long → il trade peggiore. Provate 3 varianti (vote AND, gate puro 80/20, 75/25): tutte negative (Sharpe -0.27/-0.45/-0.75). L'edge richiede CONCORDANZA DIREZIONALE (long leader/short laggardo dollar-neutral) = engine a portafoglio, non per-simbolo. E' lo stesso limite di xsmom-v1. Conclusione: xsection resta l'edge piu' forte NON sfruttato del progetto; la via corretta e' riprendere xsmom-port-v1 (backtest +29% vs -20%, ritirata solo per strumentazione paper che non registrava i trade continui), NON aggiungere gambe AND per-simbolo. #xsection #cross_sectional #concordance #portfolio_engine #falsification #backtest

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
