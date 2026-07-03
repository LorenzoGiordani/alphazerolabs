# lux-confluence-rr2-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **parent**: [[lux-0.1-beta]]
- **created**: 2026-06-22

## Tesi

La confluenza LUX e l'edge piu validato del desk: trend (tsmom) + liquidazioni reali (liq_imbalance) + forecast Kronos concordi = setup top-conviction. Questo challenger prende ESATTAMENTE quella confluenza a 3 gambe ma cambia solo l'uscita: stop ATR-adattivo + RR2 invece del RR del parent. Ipotesi (di Lorenzo): su entry ad alta convinzione un TP a 2R viene colpito molto piu spesso di RR alti, alzando il PnL realizzato senza degradare il rischio. Cambio SOLO su exit → zero rischio extra sull'entry, gia validato. Falsificata se: a parita di entry, RR2 non batte il parent (lux-0.1-beta) su Sharpe e PnL realizzato in walk-forward + paper.

## Note evoluzione

v1 — confluenza LUX 3-gambe (parent lux-0.1-beta) con exit RR2 + stop ATR3. Test mirato dell'ipotesi RR2 di Lorenzo sull'edge validato. Basket 9-asset 6m: meanSharpe 1.47, +14.66%, 8/9 positivi, worstDD -13.8% → batte i parent (tsmom-atr 1.26, lux-0.1-beta 0.65). Ipotesi RR2 confermata in backtest; il paper e il gate finale. Mutazioni: RR, stop_atr_mult, soglie delle gambe.

## Performance (paper)

- equity: $10,789.65
- trade chiusi: 9 · win rate: 33%
- PnL totale: $62.11
- posizioni aperte ora: 0

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| ETH | stopped | 1721.735645416286 | $-102.74 |
| ZEC | stopped | 441.587125193657 | $-101.55 |
| WLD | stopped | 0.5931814048441715 | $-100.95 |
| ETH | target | 1645.642791317143 | $192.77 |
| CRV | target | 0.19822570635668574 | $197.56 |
| NEAR | target | 1.938799922448 | $198.50 |
| ZEC | retired | 404.83 | $-28.28 |
| CRV | retired | 0.19189 | $-33.63 |
| XRP | retired | 1.0361 | $-11.59 |
| SOL | retired | 70.446 | $-73.47 |
| ETH | retired | 1559.0 | $-9.40 |
| NEAR | retired | 1.7891 | $19.91 |

## Lezioni

- **execution_issue** (ETH, $-102.74): Quando tsmom è negativo (-1) su un long, il segnale di momentum deve essere un veto strutturale, non un voto minoritario: al momento dell'apertura tsmom=-1 contraddiceva la direzione mentre liq_imbalance e kronos_forecast votavano 2:1. La tesi dichiarava AND logico ma il sistema ha eseguito come majority-vote, rimuovendo il filtro più persistente (momentum batte lead signals su orizzonti intraday). Imporre tsmom come veto-gate elimina i long con momentum strutturalmente avverso. #tsmom_veto #signal_aggregation_error #momentum_persistence #entry_filter #confluence_logic
- **execution_issue** (ZEC, $-101.55): In strategie AND-confluence, un segnale componente negativo è un veto assoluto: tsmom=-1 a open vietava il long indipendentemente dagli altri due segnali. Entrare con 2/3 del consenso trasforma un AND-gate in un majority-vote non dichiarato — abbassa la soglia e invalida il backtest della strategia. Regola generale: se anche un solo segnale richiesto dalla tesi è contro-direzionale all'ingresso, la trade non esiste. #and-gate-violation #signal-confluence #tsmom-veto #execution #crypto-momentum
- **thesis_wrong** (WLD, $-100.95): I segnali di confluenza tecnica su altcoin ad alta beta (WLD, SUI, etc.) devono essere filtrati dal regime direzionale del basket macro: se tsmom/lux-0.1-beta sparano short su BTC/ETH/SOL/NEAR nello stesso momento, qualsiasi long su altcoin speculativo è un fade del regime, non una confluence reale — i segnali tecnici sparano comunque perché non vedono il contesto cross-asset. Prerequisito per long altcoin: almeno BTC e ETH devono essere flat o long nel basket. #regime-mismatch #altcoin-long #confluence-false-signal #bear-market-filter #cross-asset-regime #lux-confluence-rr2-v1
- **thesis_right** (ETH, $192.77): In un vote di confluenza 2/1 dove il segnale forecast diverge da momentum e flow (come kronos=+1 contro tsmom=-1 e liq_imbalance=-1), il move direzionale tende a essere rapido e poco esteso: impostare tp1 al 50% entry-target permette di garantire profitto prima che il segnale forecast leading si materializzi in inversione. #confluence_vote #signal_divergence #partial_take_profit #forecast_vs_flow #short
- **thesis_right** (CRV, $197.56): Strategie confluence con RR≥2 su token DeFi mid-cap funzionano meglio quando più segnali si allineano prima dell'entry: il target statico 2:1 cattura il movimento medio senza inseguire l'upside, e la chiusura disciplinata al target evita il rischio di mean-reversion su asset illiquidi come CRV. Mantenere il target fisso — non alzarlo in corsa — è il vantaggio strutturale di questo setup. #confluence #defi #target_hit #rr2 #discipline
- **thesis_right** (NEAR, $198.50): Quando tsmom e kronos_forecast convergono short con liq_imbalance come conferma secondaria, il segnale di confluence ha sufficiente edge per tenere la posizione fino al target pieno senza uscite parziali anticipate: RR2 è giustificato e va rispettato. #confluence #tsmom #short #target_hit #rr2
- **execution_issue** (ZEC, $-28.28): When thesis, direction AND price path are all correct (short ZEC, price fell ~8.8% from 443.86 to 404.83, nearly hitting target 403.07) yet PnL is negative (-$28.28), the loss is purely structural — not directional. The 'retired' close on a 3+ day crypto-perp short almost certainly bled the position via cumulative positive funding payments. Actionable rule: for any confluence strategy that holds >24h on crypto perps, cap the time-stop at the point where expected funding erosion exceeds (target_distance − current_unrealized), or net the funding cost into the R:R at entry and reject trades where post-funding R:R drops below 1.5. #funding_cost_bleed #time-stop_missing #thesis_correct_pnl_negative #retired_close #crypto_perps #confluence_rr2 #structural_loss_vs_directional_win #ZEC
- **execution_issue** (CRV, $-33.63): Quando si shorta un asset con confluence parziale (2/3 segnalli allineati, 1 contro), il move atteso è per definizione attenuato: in quei casi il R:R 2:1 puro senza partial TP è subottimale perché il prezzo media si ferma prima del target. Se poi l'holding period supera le 24-48h su perp, il funding cost in regime di crowding short può invertire un trade direzionalmente corretto. Regola: su confluence 2/3 con segnale forecast opposto, aggiungere un partial TP al 50% del target (lock ~1R) entro le prime 24h, e imporre un time-stop più stretto (max 48h) per limitare l'esposizione al funding bleed. #partial_tp_missing #funding_bleed #confluence_partial #time_stop_too_loose #kronos_dissent #retired_exit
- **execution_issue** (XRP, $-11.59): Un trade chiuso con reason 'retired' (non stop_hit, non target_hit) rivela un buco di gestione: il position è stato lasciato vivere oltre la finestra della tesi senza un time-stop formale. In strategie confluence-RR2 su crypto ad alta volatilità come XRP, se entro N barre non si materializza l'estensione attesa, la probabilità condizionale del target crolla drasticamente — un time-stop esplicito (es. chiusura al 50% del tempo teorico senza progresso verso target) converte un -11.59\$ slippato in un costo controllato molto minore. #time-stop #retired-close #XRP #position-management #confluence-rr2 #crypto-volatility
- **thesis_wrong** (SOL, $-73.47): Quando un modello di "confluence" include un segnale che contraddice attivamente la direzione del trade (kronos_forecast: +1 in un short), non si ha confluence — si ha un segnale misto. Un voto conflittuale non è "1/3 neutro" ma informazione che il trade è a rischio: i regimi con 2 signal concordanti e 1 che diverge non dovrebbero mai generare un'entry full-size, specialmente se il segnale divergente è un modello di forecast direzionale. Il fix è un filtro di "unanimity on direction" o almeno una degradazione della size (50% o niente) quando uno dei componenti di un AND-based confluence punta nel senso opposto. #confluence_internal_conflict #mixed_signal_filter #kronos_divergence #direction_filter_required #short_SOL
- **execution_issue** (ETH, $-9.40): Quando un trade è generato da confluence di segnali che includono tsmom (trend-following multi-giorno), un retirement/time-stop orario fisso (es. chiusura a fine sessione) crea un mismatch strutturale: il segnale ha orizzonti di giorni ma l'esecuzione lo costringe in ore. Il time-stop deve scalare con il timeframe del segnale dominante nella confluence — o almeno il retirement policy deve differire i trade TSMOM-active alla sessione successiva invece di chiuderli piatti. #tsmom-time-mismatch #retired-too-early #time-stop-vs-signal-horizon #confluence-execution #ETH
- **thesis_right** (NEAR, $19.91): Un confluence a 3 segnali che non produce almeno 1 ATR di follow-through nelle prime 3-6h è probabilemente rumore di regime, non inversione. Il time-stop passivo ('retired') va bene per non perdere, ma è subottimale: aggiungere un trailing aggressivo (0.5 ATR) o un break-even stop dopo 2-4h se il prezzo è flat entro 0.5 ATR dall'entry, per monetizzare posizioni zombie prima che revertano. In questo trade il confluence short era direzionalmente giusto ma il mercato non era in regime bear abbastanza forte da spingere >1 ATR — distinguere 'segnali allineati in range-bound' da 'segnali allineati in trend' richiede il filtro del momentum reale nelle prime ore. #confluence-weak-followthrough #time-stop-vs-trailing #atr-followthrough-filter #near #lux-confluence-rr2-v1 #retired-exit #partial-r-capture

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
