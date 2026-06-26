# tsmom-liq-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **created**: 2026-06-14
- **family**: tsmom-liq

## Tesi

Trend confermato dalle liquidazioni reali (Coinalyze): entra solo quando TSMOM e lo sbilancio liquidazioni concordano sulla direzione (segui lo squeeze). Primo edge ortogonale robusto: 100% celle griglia battono il baseline, 7/9 coin positivi. In paper per validazione forward.

## Note evoluzione

seed di ricerca

## Performance (paper)

- equity: $9,417.92
- trade chiusi: 26 · win rate: 23%
- PnL totale: $-554.36
- posizioni aperte ora: 0

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| XRP | stopped | 1.1645024534199 | $-61.57 |
| NEAR | target | 2.2725499090979997 | $178.38 |
| NEAR | target | 2.543449898262 | $180.45 |
| WLD | stopped | 0.5799299768028 | $-62.25 |
| ZEC | stopped | 521.87847912486 | $-63.35 |
| NEAR | stopped | 2.4219974031201 | $-62.96 |
| WLD | stopped | 0.58134372674625 | $-62.56 |
| ZEC | stopped | 503.50947985962 | $-62.17 |
| CRV | stopped | 0.24065924037362998 | $-61.78 |
| WLD | stopped | 0.62587197496512 | $-61.01 |
| CRV | stopped | 0.23526749058929997 | $-61.00 |
| WLD | target | 0.6872474725101 | $174.63 |
| WLD | stopped | 0.6606599735735998 | $-61.31 |
| CRV | stopped | 0.23090924076363 | $-60.24 |
| WLD | stopped | 0.60095097596196 | $-60.53 |
| BTC | stopped | 64518.62241925499 | $-60.57 |
| NEAR | stopped | 2.1561149137554 | $-60.15 |
| WLD | stopped | 0.6267007249319699 | $-59.77 |
| WLD | stopped | 0.62494572500217 | $-59.02 |
| NEAR | stopped | 2.1533199138672 | $-58.66 |
| ETH | stopped | 1748.7524300498997 | $-58.67 |
| WLD | stopped | 0.6315367247385301 | $-57.91 |
| SUI | manual_close | 0.7091417999999999 | $25.46 |
| CRV | manual_close | 0.20814162 | $52.43 |
| XRP | manual_close | 1.13432682 | $27.02 |
| ZEC | manual_close | 452.220426 | $-37.25 |

## Lezioni

- **execution_issue** (XRP, $-61.57): Quando tsmom e liq_imbalance convergono (-1/-1) il segnale è solido, ma su asset ad alta volatilità intraday (XRP, ATR giornaliero > 3%) uno stop a ~2.5% cade dentro la banda di rumore e non fuori dalla tesi. Gli stop di momentum-liq vanno calibrati su 1.5-2x ATR del timeframe del segnale, non su una percentuale fissa: altrimenti ogni rimbalzo tecnico di 5h elimina il trade prima che la direzionalità si esprima. #stop_sizing #atr_calibration #tsmom #xrp_volatility #premature_stopout
- **execution_issue** (NEAR, $178.38): Exit price (2.2725) è sotto entry (2.3664) su un long, ma PnL registrato è +$178. Inoltre ts_close (02:00) precede opened_at (04:00) di 2 ore. Il record è strutturalmente corrotto: il sistema deve validare sign(exit_px - entry_px) == sign(pnl_usd) per i long e ts_close > ts_open prima di persistere su journal — ogni post-mortem su dati incoerenti produce lezioni spurie e degrada il backtest. #data-integrity #pnl-sign-mismatch #timestamp-inversion #logging-bug #tsmom-liq-v1
- **thesis_right** (NEAR, $180.45): Quando tsmom e liq_imbalance convergono entrambi a +1 (signal_vote pieno), il trade ha sufficiente conviction per giustificare R:R ≥ 3:1 con target fisso: uscire anticipatamente o ridurre il target per 'sicurezza' sarebbe stato un errore atteso-negativo. La confluenza momentum + order-flow su alt-L1 genera move intraday completi — non scalare out prima del target. #signal_confluence #tsmom #liq_imbalance #alt_l1 #intraday_momentum #full_target
- **thesis_wrong** (WLD, $-62.25): segnali tsmom+liq_imbalance su token narrativi a bassa capitalizzazione catturano spesso momentum di brevissimo termine (spike di liquidità) che si esaurisce entro poche candele: senza un filtro di regime (BTC sopra MA su H4, settore AI/L1 in risk-on) il segnale long su altcoin volatili ha tasso di falsi positivi strutturalmente alto e va ridotto in size o saltato #tsmom #false_positive #regime_filter #narrative_token #altcoin #low_cap
- **execution_issue** (ZEC, $-63.35): Doppio segnale confluente (tsmom+liq entrambi=1) su un alt ad alta volatilità segnala potenziale entry affollato: molti sistemi sistematici ricevono lo stesso trigger simultaneamente, e uno stop fisso al 2.5% viene colpito dal noise di mean-reversion prima che la tesi si dispieghi. Regola generale: su alt con ATR/day ≥ 3%, calibrare lo stop a 1× ATR(14) e ridurre la size proporzionalmente; in alternativa, attendere un micro-pullback dal primo tick di segnale per entry meno denso. #stop_sizing #atr_calibration #crowded_entry #signal_confluence #altcoin_volatility #execution
- **execution_issue** (NEAR, $-62.96): Quando tsmom + liq_imbalance si allineano su altcoin ad alta beta (NEAR, SOL-tier), uno stop fisso <3% viene consumato dal rumore intraday prima che il momentum si materializzi: il minimo stop deve essere ≥1.5× ATR daily del simbolo; in alternativa ridurre la size proporzionalmente per mantenere il risk assoluto costante con uno stop più largo. #stop_calibration #atr_sizing #tsmom #liq_imbalance #altcoin_noise
- **execution_issue** (WLD, $-62.56): Un segnale tsmom è per definizione costruito su finestre giornaliere (o multi-ora): lo stop deve essere ≥ 1× ATR-giornaliero del sottostante, altrimenti il rumore intraday esaurisce il margine prima che la tesi si materializzi. WLD ha ATR-daily ~5-8%; uno stop al 2.5% sotto l'entry entra direttamente nella fascia di rumore e viene colpito statisticamente anche quando la direzione è corretta. Regola generale: su strategie momentum a bassa frequenza, calibra lo stop sul timeframe del segnale (daily ATR), non sulla tolleranza di rischio in USD — aggiusta il size per tenere il rischio fisso, non restringere lo stop. #tsmom #stop-calibration #atr-mismatch #signal-timeframe #crypto-momentum #size-vs-stop-tradeoff
- **thesis_wrong** (ZEC, $-62.17): In fasi di downtrend strutturale su altcoin ad alta beta (ZEC), segnali tsmom+liq_imbalance rialzisti catturano spesso picchi di crowding long piuttosto che momentum genuino: il segnale si accende quando tutti sono già entrati, non quando inizia la spinta. Richiedere un regime-filter esplicito (es. BTC price > MA20 o rolling-Sharpe basket > 0) prima di approvare long su tsmom in altcoin. #tsmom #false-momentum #altcoin-beta #regime-filter #crowding-peak #ZEC
- **execution_issue** (CRV, $-61.78): Segnali tsmom+liq_imbalance su token DeFi small-cap richiedono un filtro di regime esplicito: in mercato bear/laterale, gli squilibri di liquidità su CRV-class asset sono noise e non segnale direzionale — long momentum senza conferma macro (es. BTC sopra EMA breve o realized-vol sotto soglia) producono whipsaw sistematici il cui stop-rate supera l'alpha atteso del setup. #tsmom #regime_filter #defi_small_cap #whipsaw #liq_imbalance #bear_regime
- **execution_issue** (WLD, $-61.01): Su altcoin ad alta volatilità (WLD, float basso), uno stop fisso %-based ignora l'ATR del timeframe: un'oscillazione di 2.5% in 1h è rumore ordinario, non invalidazione della tesi. I segnali tsmom+liq_imbalance erano coerenti ma lo stop è stato piazzato dentro il noise-band — regola: stop su tsmom-liq entries deve essere ≥1× ATR(4h) per sopravvivere al mean-reversion intra-candle senza che la tesi direzionale venga falsificata. #stop_sizing #atr_calibration #tsmom #liq_imbalance #altcoin_volatility #noise_vs_signal
- **thesis_wrong** (CRV, $-61.00): tsmom + liq_imbalance simultanei su token DeFi (bassa cap, alto crowding) possono riflettere momentum già esaurito al momento del segnale — non un'accelerazione in corso. Regola generale: in regime neutro/bear su BTC, esigere N ore di persistenza del segnale (es. 2+ candle di conferma) e coerenza col trend ETH prima di entrare long su DeFi; un segnale intracandle fermato in <1h indica che la liq_imbalance era noise temporaneo, non pressione direzionale sostenuta. #tsmom #liq_imbalance #signal_staleness #defi_crowding #regime_filter #entry_timing
- **execution_issue** (WLD, $174.63): Il PnL (+$174.63 su $2390.57 = 7.3%) è coerente con un fill al target (0.7286, +7.5%) ma exit_px registra 0.6872 (+1.4%) — discrepanza ~5x: il logger sta scrivendo il mark price al momento del log invece del fill price simulato. Aggravante: close.logged_at (20:16) precede open.logged_at (21:15) e open_ts == close_ts (stesso candle), indicando race condition nel pipeline. In paper trading, separare rigorosamente fill_px (prezzo di esecuzione deterministico, fissato all'istante del segnale) da mark_px (prezzo corrente al momento del log); finché il campo è ambiguo ogni post-mortem futuro è invalido indipendentemente dalla direzione del mercato. #logging_bug #exit_px_mismatch #timestamp_race_condition #paper_trading_accounting #tsmom_liq #data_quality
- **execution_issue** (WLD, $-61.31): Su token illiquidi ad alta volatilità (WLD-class), uno stop fisso al 2.5% rientra nel rumore di breve periodo: il trade è stato stoppato in 12h su movimento di ~1.7bp dal close. Gli stop devono essere calibrati sull'ATR dell'asset specifico (minimo 1×ATR daily), non su una percentuale flat derivata da asset più liquidi come BTC/ETH — altrimenti il segnale corretto viene annullato da volatilità casuale prima che la tesi possa esprimersi. #stop-sizing #atr-calibration #illiquid-altcoin #tsmom #noise-stop
- **thesis_wrong** (CRV, $-60.24): tsmom+liq_imbalance=1 su governance DeFi token con distribuzione strutturale (ve-overhang, TVL/fees in calo) cattura un ingresso crowded, non momentum organico: tutti i sistemi sistematici ricevono lo stesso trigger simultaneamente, il liq_imbalance=1 riflette gli ordini degli altri modelli tsmom, non domanda spot genuina, e la mean-reversion avviene entro 12-24h prima che la tesi si dispieghi. Regola generale: su DeFi governance token, esigere tsmom positivo su lookback ≥30g (non solo 7g) E conferma che il ratio DeFi-sector/BTC sia in uptrend settimanale prima di considerare liq_imbalance una conferma valida. #tsmom #defi_governance_token #crowded_entry #structural_decline #regime_filter #ve_overhang #false_signal
- **execution_issue** (WLD, $-60.53): Su altcoin ad alta volatilità (WLD), uno stop fisso del 2.5% sotto entry è insufficiente per assorbire il rumore intra-candle: il trade è stato stopped in 2 ore nonostante segnali coerenti (tsmom=1, liq_imbalance=1). Lo stop dovrebbe essere calibrato sull'ATR dell'asset (es. 1.5–2× ATR_1h) — non su una percentuale uniforme — per evitare che il rumore di mercato esaurisca il risk budget prima che la tesi abbia tempo di esprimersi. #stop_calibration #atr_sizing #altcoin_volatility #tsmom #premature_exit
- **thesis_wrong** (BTC, $-60.57): Segnali tsmom + liq_imbalance entrambi -1 dopo un declino prolungato rischiano di entrare sull'esaurimento del momentum, non sulla sua continuazione: il mercato già posizionato short inverte appena la pressione sell si esaurisce. Richiedere come filtro che il prezzo sia ancora sotto il midpoint dell'ultimo range significativo (es. 5d) prima di aprire short con questi segnali riduce il rischio di mean-reversion trap. #momentum_exhaustion #tsmom #liq_imbalance #mean_reversion_trap #crowded_short #entry_filter #bear_regime
- **thesis_wrong** (NEAR, $-60.15): Un segnale tsmom+liq_imbalance long su un altcoin L1 ad alto beta (NEAR, APT, AVAX) in un regime macro risk-off — evidenziato da segnali short contemporanei su BTC e materie prime nello stesso basket — cattura momentum residuo di distribuzione, non l'inizio di un trend: il prezzo inverte immediatamente perché i buyer di momentum vengono assorbiti dai seller istituzionali che scaricano. Regola: aggiungere un regime-gate cross-asset (es. tsmom_basket_mean > 0) come condizione necessaria per aprire long su altcoin ad alta correlazione-BTC; in assenza di regime bullish, il segnale viene scartato o la size dimezzata. #tsmom #regime-filter #high-beta-altcoin #macro-bear #signal-exhaustion #liq-imbalance
- **execution_issue** (WLD, $-59.77): Uno stop a 1.27x ATR (2.5% stop_pct_eff su ATR 1.97%) non filtra il rumore intraday per strategie tsmom: il trade è stato fermato in <40 minuti prima che la direzionalità del momentum potesse prevalere. Le strategie tsmom richiedono stop di almeno 1.5–2x ATR per sopravvivere alla volatilità di apertura sessione; restringere lo stop per limitare il rischio nominale produce in realtà stop-rate più alto e EV negativo. #tsmom #stop_calibration #atr_multiple #execution #intraday_noise
- **execution_issue** (WLD, $-59.02): Stop a 1.27x ATR (2.5% stop con ATR 1.97%) è insufficiente per una strategia momentum: il trade viene espulso da normale volatilità intra-sessione prima che il segnale possa svilupparsi. Le strategie tsmom richiedono stop ≥ 1.5-2x ATR per sopravvivere al noise; sotto quella soglia anche un segnale direzionalmente corretto (tsmom=1, liq_imbalance=1 entrambi allineati) produce perdite strutturali per shake-out, non per tesi sbagliata. #stop_too_tight #atr_ratio_insufficiente #tsmom #noise_stop #sizing
- **execution_issue** (NEAR, $-58.66): Strategie tsmom con doppia conferma (tsmom + liq_imbalance entrambi -1) richiedono stop ≥ 2× ATR: uno stop a 1.4× ATR (2.5% vs ATR 1.79%) viene consumato dal rumore intraday nelle prime ore prima che il momentum abbia tempo di dispiegarsi; il segnale può essere corretto ma il trade muore per granularità sbagliata del risk parametrization. #tsmom #stop_sizing #atr_multiplier #execution #momentum_lag
- **execution_issue** (ETH, $-58.67): Segnali tsmom+liq_imbalance validi al momento dell'entry vengono sistematicamente puliti quando l'apertura avviene in finestre thin-book (23:00-01:00 UTC): con ATR orario dello 0.63%, uno stop a 2.5% equivale a ~4x ATR, ma in mercati sottili una singola controparte può coprire l'imbalance e reverire il prezzo di 4x ATR in meno di 2 ore prima che la tesi abbia tempo di svilupparsi. Regola: in finestre di liquidità ridotta, o si posticipa l'entry alla sessione principale (07:00-16:00 UTC) o si riduce la size del 50% e si allarga lo stop a ≥6x ATR per assorbire il noise thin-book. #thin-market-timing #stop-placement #liquidity-window #tsmom #entry-timing
- **thesis_wrong** (basket, —): Ritirata da challenger: 21 trade paper, meanR -0.455 (perdente). Il paper trading ha falsificato l'edge. #lifecycle #retire #paper
- **execution_issue** (WLD, $-57.91): Con ATR > 2%, uno stop a 0.95× ATR (come in questo trade: stop_pct_eff 2.5% vs ATR 2.63%) viene bruciato dal rumore di singola candela prima che il momentum si materializzi; per tsmom su altcoin ad alta volatilità, stop minimo 1.5× ATR oppure entry scaglionata con size ridotta finché il prezzo non conferma oltre l'entry di almeno 0.5× ATR. #tsmom #stop-sizing #atr-calibration #altcoin-noise #execution
- **execution_issue** (SUI, $25.46): Con tsmom + conferma liq_imbalance entrambi -1, la chiusura manuale prima del time-stop o del target erode sistematicamente l'EV: i vincitori vengono tagliati presto mentre i perdenti arrivano allo stop pieno. Il segnale era direzionalmente corretto (SUI sceso da 0.7172 a 0.7091), ma catturare solo ~15% del target pianificato svela che il regime di momentum era debole o si stava esaurendo. Regola generale: per strategie tsmom con R:R 3:1, se il prezzo non raggiunge il 50% del target entro metà del time-window atteso, chiudere a flat è difendibile; ma la chiusura discrezionale in profitto senza trigger esplicito va codificata come exit-rule nel backtest, non lasciata a giudizio. #tsmom #execution_override #manual_close #ev_erosion #momentum_decay #exit_discipline
- **execution_issue** (CRV, $52.43): In dual-signal tsmom+liq_imbalance shorts con R:R 3:1, la chiusura manuale al 30% del target (entry 0.2130 → exit 0.2081 vs target 0.1970) distrugge l'EV atteso: il bordo statistico di queste strategie è concentrato nel tail del move, non nei primi tick favorevoli. Override manuale solo su invalidazione esplicita dei segnali, mai su profit parziale. #tsmom #liq_imbalance #manual_close #execution #short #r_r_degradation #momentum_tail
- **execution_issue** (XRP, $27.02): Con tsmom e liq_imbalance entrambi allineati (-1/-1) il setup ha edge confermato dalla tesi: uscire manualmente a -1.2% su un target di -7.5% (R:R 1:3) tronca la distribuzione di payoff e converte un'opportunità statistica in un raccatto di rumore. Regola generale: exit only on stop, target, o inversione esplicita dei segnali — il manual_close senza cambio di segnale è un override emozionale che erode l'EV atteso della strategia sistematica. #execution_discipline #early_exit #payoff_truncation #tsmom_liq #manual_override #signal_aligned_exit
- **execution_issue** (ZEC, $-37.25): Sovrascrivere con manual_close un trade sistematico (segnali ancora attivi, stop non toccato) distrugge l'edge stimato nel backtest: la strategia tsmom-liq-v1 aveva stop e target calibrati sull'ATR; uscire discrezionalmente a metà strada trasforma un expected-value positivo in una perdita certa a R parziale. Regola generale: l'override manuale è legittimo solo se almeno uno dei segnali costitutivi si è invertito o se c'è un evento strutturale; il drawdown intraday entro lo stop non è un trigger valido. #execution-discipline #manual-override #systematic-trading #tsmom #premature-exit

## Eventi lifecycle

- **retire** (2026-06-22): 

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
