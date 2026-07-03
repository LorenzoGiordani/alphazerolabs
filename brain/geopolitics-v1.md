# geopolitics-v1

[[README|← Brain index]]

## Anagrafica

- **status**: champion
- **created**: 2026-06-19
- **family**: geopolitics

## Tesi

Layer LLM cross-asset gated sugli eventi geopolitici. news_event(geopolitics) — burst GDELT su war/sanctions/conflict/military — fa da TRIGGER: solo quando scoppia un catalizzatore il desk ragiona. L'edge non è il sentiment (tone falsificato come predittore, event study 2026-06-13, tone_hit 0.38<0.50) ma l'interpretazione del CANALE DI TRASMISSIONE: guerra/sanzioni → energia (oil, natgas), risk-off → safe-haven (gold) e deleveraging crypto. Il desk sceglie asset e direzione dal nesso causale, non dal segno del tono. Falsificata se: i trade gated-su-geopolitica NON battono il buy&hold cross-asset sullo stesso periodo → il catalizzatore non aggiunge edge sopra il drift.

## Note evoluzione

v1 — gate news_event(geopolitics) + desk LLM cross-asset. Prima strategia engine:desk. Possibili mutazioni: soglia min_z del burst, finestra max_age_h, universo (aggiungere indici/FX), default di exit.

## Performance (paper)

- equity: $9,983.36
- trade chiusi: 7 · win rate: 43%
- PnL totale: $-14.36
- posizioni aperte ora: 0

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| xyz:NATGAS | time_stop | 3.2873424 | $85.51 |
| ETH | time_stop | 1577.3154 | $42.78 |
| ETH/USD | dedup_fix (bug canonical: fantasma chiave ETH/USD vs ETH) | 1577.88436 | $0.00 |
| xyz:GOLD | stopped | 3979.7548408098 | $-155.81 |
| ETH | time_stop | 1585.01694 | $-4.53 |
| BTC | time_stop | 58722.7422 | $35.95 |
| xyz:NATGAS | time_stop | 3.25724842 | $-1.98 |
| xyz:NATGAS | time_stop | 3.25724842 | $-1.98 |
| xyz:CL | time_stop | 69.80603599999999 | $-16.28 |

## Lezioni

- **thesis_right** (basket, —): Promossa a CHAMPION: 52 trade paper, basket_sharpe 0.989, DSR None, win 0.02, PnL 83.79$. Primo champion della famiglia. #lifecycle #promote #paper #champion
- **thesis_right** (xyz:NATGAS, $85.51): Quando una tesi miscela catalyst tattici (geopolitica, ~48-72h) con fattori strutturali multi-week (El Niño, scorte stagionali), il time-stop deve essere tarato sul componente PIÙ LENTO della tesi, non su quello più veloce. Alternativamente, se si vuole mantenere un time-stop corto, la tesi deve essere spogliata ai soli driver coerenti con quell'orizzonte. Un time-stop a 72h su una tesi che si appoggia pesantemente su driver multi-week garantisce uscite premature — profitable ma sistematicamente sub-target. Rule of thumb: se rimuovi dalla tesi il fattore più lento e la tesi non sta in piedi da sola, il time-stop è sotto-dimensionato. #time-horizon-mismatch #mixed-catalyst-thesis #time-stop-calibration #natgas #geopolitics-v1 #structural-vs-tactical #profitable-sub-target
- **thesis_right** (ETH, $42.78): In trade macro/deleveraging con time-stop stretto (≤72h), il target deve essere calibrato sulla velocità realistica del canale, non sull'R:R desiderato. Un 'canale deleveraging graduale' su ETH giustifica ~5-8% in 72h, non -15%. Se vuoi mantenere il target al -15%, devi allentare il time-stop a 5-7 giorni o scalare l'uscita (50% a -5%, trail sul resto). Regola: target/time-stop mismatch = stai implicitamente scommettendo su un regime (flash crash) che la tua stessa tesi non descrive. #target_calibration #time_stop_discipline #deleveraging_regime #R:R_illusion #ETH #macro_short
- **execution_issue** (ETH/USD, $0.00): Un bug di canonicalizzazione degli symbol key (ETH/USD vs ETH) ha causato la chiusura forzata del trade a PnL zero, indipendentemente dalla tesi. Il rischio non era di mercato ma di infrastruttura: il dedup engine deve validare la normalizzazione dei symbol prima dell'apertura, non dopo. Regola: ogni coppia di symbol che differisce solo per suffisso/delimiter deve essere mappato a UNA chiave canonica al momento dell'inserimento, con fallback reject se la mappatura fallisce — mai affidarsi al fix retroattivo. #infra-bug #symbol-canonicalization #dedup #zero-pnl #eth-usd
- **thesis_wrong** (xyz:GOLD, $-155.81): Non esiste 'asimmetria netta' nel safe-haven trade durante stress di liquididità. La tesi claimsva che entrambi gli scenari (persistenza o fade del risk-off) lasciavano un lato protetto, ma il gold è stato trascinato nel deleveraging cross-asset entro 56h. Lesson: quando una tesi safe-haven long dipende dalla decoupling assumption (gold ≠ risk assets), il scenario di invalidazione 'correlation spike to 1' non è un tail event da citare e ignorare — è lo scenario più probabile in regime di stress acuto, perché le liquidazioni forzate vendono TUTTO incluso l'asset 'sicuro' per meet margin call. Regola actionable: se la tesi si regge sull'asimmetria 'entrobi gli scenari mi favoriscono', riduci il size del 50% rispetto al normale o inserisci un micro-hedge (es. long VIX o short equity index) che paga proprio nel regime correlation-1 che rompe la tesi. L'asimmetria claimsvata è quasi sempre overfitting narrativo sul hindsight di un singolo burst. #gold #safe-haven #correlation-spike #asymmetry-bias #risk-off #geopolitics-v1 #liquidation-risk #sizing-bypass
- **thesis_wrong** (ETH, $-4.53): I fade geopolitici su crypto basati su un solo segnale GDELT (Z=2.0) falliscono quando la catena causale "shock → risk-off → deleveraging crypto" ha troppi nodi intermedi non verificati. Il burst era rumore senza follow-through — esattamente lo scenario di invalidazione elencato nella tesi — eppure il trade è stato aperto senza attendere alcuna conferma di trasmissione nel microstruttura crypto (funding spike, volume surge, correlation break vs BTC). Lesson generale: in strategie geopolitiche su asset indiretti (crypto non è il primo veicolo di risk-off), l'entry deve essere gated da un segnale di conferma nel target asset stesso — non basta il catalyst macro, serve evidence che il meccanismo di trasmissione si sia attivato. Senza gate di conferma, si tradisce un'ipotesi non testata con size piena. #geopolitics-v1 #transmission-mechanism #confirmation-gate #crypto-risk-off #thesis-vs-invalidation-discipline #time-stop
- **thesis_right** (BTC, $35.95): Nei fade geopolitici su crypto, il time-stop (72h) è spesso più importante del target fisico: il deleveraging meccanico è un burst di intensità decrescente, non un trend persistente. Se entro 48-72h il prezzo non ha raggiunto il target, la pressione di vendita si è esaurita e il carry del posizionamento corto diventa negativo. Ridurre il target al 50% dell'AEA e stringere il time-stop a 48h migliora il risk-reward in questi scenari. #geopolitics #crypto #time-stop #deleveraging #btc #fade #risk-off
- **thesis_wrong** (xyz:NATGAS, $-1.98): Essere 'l'unico asset con momentum positivo' in tape risk-off è informazione ambigua: può indicare flusso direzionale genuino, ma anche semplice inerzia/lag dove il commodity non ha ancora liquidato come il resto. Un segnale LUX+tsmom su NG senza un catalizzatore specifico (inventory report, weather shift, pipeline event) entro la finestra di time-stop produce di frequente chop morto: il momentum relativo non si traduce in momentum assoluto. Lezione: per trade tsmom su commodity in regime risk-off, richiedere oltre al signal alignment anche (a) un catalizzatore calendarizzato entro il time-stop window, oppure (b) un time-stop più lungo (120-168h) che permetta al trend di svilupparsi — 72h su NG è spesso troppo stretto e cattura solo noise di consolidamento post-segnale. #tsmom_commodity #risk_off_relative_strength #time_stop_calibration #lux_signal_follow_through #natural_gas #momentum_ambiguity
- **thesis_wrong** (xyz:CL, $-16.28): In un regime bear con tsmom -1 e vol-compression, andare long su un catalyst geopolitico richiede che lo shock sia già cinetico e pricing-breaking entro le prime 12-24h. Se il premium non esplode immediatamente (CL si è mosso -0.7% in 96h), il mercato sta dicendo che la disruption non è credibile o è già priced-in. Il "short squeeze contro trend-follower" è una narrazione seducente ma spesso illusoria in regime bear: i trend-follower sono lì perché i fondamentali sono bearish, e un headline shock viene tipicamente venduto, non comprato. La lesson generale: i trade long-exogenous-catalyst contro tsmom -1 hanno un窗口 di edge strettissimo (sub-24h); se il move non arriva entro la prima sessione, l'edge è evaporato e il time-stop va accorciato drasticamente, non esteso a 96h. #geopolitics #tsmom-contrarian #bear-regime #short-squeeze-narrative #time-stop #war-risk-premium #vol-compression #CL

## Eventi lifecycle

- **promote** (2026-06-26): 

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
