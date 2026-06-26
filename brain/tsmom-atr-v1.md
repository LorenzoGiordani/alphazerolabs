# tsmom-atr-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **parent**: [[tsmom-v1]]
- **created**: 2026-06-21
- **family**: tsmom-atr

## Tesi

Stessa tesi TSMOM del parent, ma stop volatility-adaptive (k*ATR invece di % fissa) e RR 2 invece di 3. Ipotesi: lo stop ATR sopravvive al rumore senza essere troppo largo, e un TP a 2R viene ittato molto più spesso di 3R. Falsificata se: su basket misto crypto+commodities non batte il parent (tsmom-v1, RR3 stop fisso) su Sharpe e consistenza fold in walk-forward + paper.

## Note evoluzione

Mutazione exit di tsmom-v1: stop_atr_mult 3.0 + target_r 2.0 (no partial: su trend lento frammenta). In A/B 6m/6-asset dava più rendimento del parent (meanRet +8.5% vs +4.9%) ma Sharpe inferiore (0.64 vs 0.97) → il paper gate decide.

## Performance (paper)

- equity: $9,324.90
- trade chiusi: 26 · win rate: 23%
- PnL totale: $-1,021.27
- posizioni aperte ora: 0

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| xyz:BRENTOIL | stopped | 83.17778238717428 | $-103.55 |
| xyz:CL | stopped | 79.76113966669713 | $-103.19 |
| xyz:XYZ100 | stopped | 30224.118791035202 | $-112.91 |
| xyz:SKHX | stopped | 1861.0927826991426 | $-103.45 |
| xyz:SILVER | stopped | 65.0902116821057 | $-105.85 |
| xyz:DRAM | stopped | 78.19406830080857 | $-102.93 |
| xyz:MU | stopped | 1125.7785263974283 | $-104.10 |
| xyz:SP500 | stopped | 7446.67920213282 | $-112.78 |
| xyz:SILVER | stopped | 65.20664024887714 | $-95.99 |
| HYPE | stopped | 65.75306879844855 | $-101.89 |
| XRP | stopped | 1.1534856681462855 | $-95.33 |
| ZEC | stopped | 465.15426710811425 | $-99.03 |
| XPL | stopped | 0.08511592516679142 | $-100.71 |
| NEAR | stopped | 2.0690213458105715 | $-99.82 |
| xyz:SILVER | target | 64.15342600529142 | $153.85 |
| xyz:HOOD | stopped | 101.14956738258857 | $-86.56 |
| WLD | stopped | 0.5853249765870001 | $-101.05 |
| EIGEN | stopped | 0.25189598992416 | $-92.93 |
| ETH | target | 1680.5713613485716 | $173.69 |
| BTC | target | 62347.42607753143 | $176.76 |
| HYPE | stopped | 62.380568933348584 | $-90.24 |
| xyz:NATGAS | stopped | 3.2299855850862857 | $-89.65 |
| xyz:GOLD | target | 4091.005550645485 | $146.81 |
| xyz:SPCX | stopped | 154.7804223802114 | $-85.90 |
| xyz:BRENTOIL | target | 75.709396971624 | $151.60 |
| cash:WTI | target | 70.67342574449145 | $163.88 |

## Lezioni

- **thesis_wrong** (xyz:BRENTOIL, $-103.55): I segnali tsmom su commodity energetiche (Brent Oil) derivati da lookback multi-giorno non assorbono impulsi intraday da report inventari, movimenti OPEC o catalyst geopolitici: il segnale -1 era già obsoleto al momento dell'entry alle 14:00 UTC. Regola generale: sui future energy, bloccare l'entry tsmom nelle 4 ore precedenti/successive a release schedule note (EIA, API, OPEC), oppure richiedere conferma del segnale su timeframe più corto (≤4h) per filtrare i falsi breakout di momentum in regime di alta event-density. #tsmom #energy_commodity #news_risk #event_filter #false_momentum #short_lived_signal
- **thesis_wrong** (xyz:CL, $-103.19): Un segnale tsmom short su commodity energetiche che tocca lo stop entro la prima sessione (< 8h) indica che il momentum misurato riflette un trend già esaurito al momento dell'entry. Filtro pratico: non aprire short tsmom-atr se il prezzo di entry è già superiore al massimo delle ultime 4 barre dello stesso timeframe — condizione che segnala un micro-reversal in corso prima ancora dell'apertura. Alternativa: richiedere un secondo segnale cross-asset (DXY, spread crack) nella stessa direzione prima di entrare su CL. #tsmom #crude_oil #stale_momentum #early_stop #entry_filter #commodity
- **thesis_wrong** (xyz:XYZ100, $-112.91): Un segnale tsmom in regime di ATR compresso (ATR_pct 0.14%) ha rapporto segnale/rumore troppo basso: la deriva di prezzo che innesca il segnale è dello stesso ordine del noise intra-giornaliero, non di un trend sostenuto. Filtrare le entry tsmom richiedendo ATR_pct > soglia minima (es. 0.25% su timeframe 1h) prima di aprire posizione: momentum reale ha bisogno di volatilità sufficiente per esprimersi oltre il rumore. #tsmom #low-atr-regime #false-momentum #volatility-filter #signal-quality
- **thesis_wrong** (xyz:SKHX, $-103.45): Un segnale tsmom con un solo lookback allineato (signals_last: {tsmom: 1}) non distingue tra momentum genuino e mean-reversion noise: il trade viene aperto al picco locale e lo stop ATR — calibrato su volatilità recente — viene mangiato dal primo pullback intraday. Richiedere consenso su almeno due finestre temporali distinte (es. 1m + 3m tsmom entrambi positivi) prima di entrare filtra i falsi segnali senza ridurre significativamente il numero di setup validi. #tsmom #false_signal #single_lookback #multi_timeframe_filter #entry_timing
- **execution_issue** (xyz:SILVER, $-105.85): Per segnali tsmom con lookback ≥1d, uno stop 3×ATR-daily è insufficiente se il trade viene eseguito intraday: il rumore infragiornaliero supera sistematicamente la stop-distance prima che il segnale abbia tempo di manifestarsi — usare 5×ATR oppure un filtro temporale minimo (≥4h dalla entry) prima che lo stop diventi operativo. #tsmom #atr-stop #commodity #intraday-noise #stop-sizing #time-filter
- **thesis_wrong** (xyz:DRAM, $-102.93): Segnali tsmom su asset con ATR molto basso (< 1% del prezzo) in sessione singola hanno alta frequenza di falsi break: il momentum è strutturalmente rumoroso in regime low-vol perché basta un piccolo selloff per toccare lo stop a 3 ATR. Filtro correttivo: richiedere che il prezzo chiuda positivo rispetto all'entry dopo le prime 4 ore prima di mantenere la posizione piena (altrimenti ridurre la size del 50% o non entrare). #tsmom #low-vol-filter #false-breakout #atr-sizing #session-confirmation
- **thesis_wrong** (xyz:MU, $-104.10): Un segnale tsmom isolato su singolo asset (senza conferma di regime settoriale o breadth) è sufficiente per aprire ma non per mantenere: quando il mercato è in fase correttiva intraday, il follow-through di un segnale 1-barra cade sotto il 50%. Aggiungere un filtro di regime (es. SPY tsmom ≥ 0 O breadth semicon > 0.5) prima dell'ingresso riduce i false positivi senza sacrificare i winner veri. #tsmom #false-breakout #regime-filter #single-signal-risk #semiconductor #intraday-reversal
- **execution_issue** (xyz:SP500, $-112.78): tsmom è un segnale di orizzonte multi-giorno: usare uno stop intra-sessione calibrato su ATR breve (0.5% su SP500, ~4.5× ATR hourly) disaccoppia l'orizzonte di uscita da quello del segnale, producendo stop-out sistematici prima che il momentum si manifesti. Regola: stop width deve essere ≥ 1× daily-ATR (≈1–1.5% su SP500) quando il segnale ha lookback >1 giorno, oppure il trade deve essere gestito su time-stop giornaliero anziché stop-loss stretto. #tsmom #signal-horizon-mismatch #stop-sizing #SP500 #whipsaw
- **execution_issue** (xyz:SILVER, $-95.99): Segnali tsmom calibrati su barre daily entrati alla transizione di sessione (23:00 UTC per i metalli) incontrano un ATR effettivo 2-3× superiore al parametro daily usato per il sizing dello stop: lo stop 1.2% (nominalmente 3× ATR) viene divorato dalla volatilità microstruttuale dell'apertura Asia in meno di un'ora. La tesi direzionale (momentum ribassista su SILVER) potrebbe essere corretta su orizzonte daily ma l'entry window è strutturalmente avvelenata. Fix: filtrare gli entry nei ±30 min attorno al cambio sessione oppure applicare un moltiplicatore ATR adattivo (es. ×2) per le prime 2 barre di ogni nuova sessione. #tsmom #session-transition #atr-sizing #overnight-volatility #entry-timing #silver
- **execution_issue** (HYPE, $-101.89): Su asset perp ad alta volatilità con wick frequenti, uno stop a 3× ATR (4.67%) viene colpito da spike di liquidità intracandle prima che il trend si sviluppi; tsmom su asset < 30-day vol > 80% richiede stop minimo 5× ATR oppure entry confermata al close della candela segnale per evitare wick-stop a PnL positivo teorico. #tsmom #stop-too-tight #wick-stop #atr-multiplier #high-vol-perp #logging-bug
- **execution_issue** (XRP, $-95.33): Lo stop ATR su strategie tsmom deve essere calibrato sull'half-life del segnale, non sulla volatilità intraday: 3×ATR a breve termine (~0.65% per tick) produce uno stop al 1.94% su un segnale che richiede giorni per realizzarsi — il trade è stato chiuso in 14h da rumore normale prima che il trend si sviluppasse. Per segnali tsmom su crypto usare time-stop primario (es. 48-72h) + stop wide (≥5×ATR o 3-4% flat) oppure verificare che il lookback del segnale sia compatibile con l'orizzonte di holding effettivo. #tsmom #stop-calibration #holding-period-mismatch #execution #crypto-noise
- **thesis_wrong** (ZEC, $-99.03): Un segnale tsmom -1 generato su un altcoin illiquido (ZEC) mentre il mercato principale è in recovery produce falsi breakout ribassisti: il momentum è già esaurito prima dell'entry. Filtrare i segnali tsmom short richiedendo allineamento direzionale del benchmark (BTC/ETH) elimina questa categoria di stop-out prematuri senza sacrificare il regime trend vero. #tsmom #regime_filter #momentum_exhaustion #altcoin_illiquidity #btc_alignment
- **thesis_wrong** (XPL, $-100.71): Un segnale tsmom=1 su un asset a bassa liquidità (XPL, prezzo <0.10) non è sufficiente come trigger standalone: il breakout momentaneo viene assorbito dallo spread/slippage e inverte in meno di 30h. Regola generale: per tsmom su micro-cap/illiquid, richiedere conferma su almeno due timeframe o volume superiore alla media mobile 20-periodo prima di aprire; altrimenti il segnale cattura rumore, non trend. #tsmom #false_breakout #illiquid #micro_cap #whipsaw #signal_confirmation
- **thesis_wrong** (NEAR, $-99.82): tsmom long su altcoin high-beta (ATR_pct >1.5%) con segnale singolo-timeframe ha alta frequenza di whipsaw: il momentum non si è materializzato in 28h, suggerendo assenza di regime trend. Regola generale: un segnale tsmom=1 su asset ad alta volatilità richiede conferma di regime (es. BTC sopra EWM a 20 periodi o breadth positiva sul basket) prima dell'entrata; senza filtro di regime il segnale è rumore in mercati laterali o bear. #tsmom #regime-filter #altcoin-whipsaw #high-beta #false-signal #single-timeframe
- **thesis_right** (xyz:SILVER, $153.85): Nei momentum short su commodity liquide con segnale tsmom=-1 confermato, target ATR a ~1.7R si risolve intraday senza bisogno di TP parziali: la prima gamba di momentum tende a esaurirsi vicino al target strutturale, e la piena size portata a scadenza massimizza l'EV rispetto a uscite scalate che diluiscono il R:R senza ridurre materialmente il rischio. #tsmom #momentum-follow #commodity #short #atr-sizing #full-target #intraday-resolution
- **execution_issue** (xyz:HOOD, $-86.56): Un segnale tsmom su equity USA che si materalizza alle 22:00 UTC (18:00 ET, after-hours) porta un disallineamento di regime: lo stop ATR è calibrato sulla volatilità di sessione regolare, ma l'after-hours ha spread più ampi, liquidità frammentata e price action guidata da partecipanti diversi. Il segnale era plausibile (momentum positivo su HOOD), ma i parametri di esecuzione non erano adattati al regime after-hours — il trade ha toccato lo stop in 5 ore senza che la tesi avesse avuto modo di esplicarsi alla riapertura. Regola generale: per equity USA, o si ritarda l'ingresso all'apertura della sessione successiva, o si allarga lo stop di almeno 1.5–2× ATR quando si entra fuori orario regolare. #tsmom #equity #after-hours #regime-mismatch #stop-calibration #entry-timing
- **thesis_wrong** (WLD, $-101.05): I segnali tsmom positivi su altcoin narrative-driven (bassa liquidità, float concentrato come WLD) in regime macro debole catturano crowding tardivo, non trend genuino: molti follower del segnale entrano contemporaneamente creando un picco di prezzo effimero che si inverte subito. Soluzione: aggiungere un filtro regime strutturale (es. asset > MA200 o regime-score > 0.5) come gate obbligatorio prima di aprire tsmom long su altcoin — se il filtro fallisce, saltare il trade anche con segnale tsmom=1. #tsmom #altcoin #crowding #regime_filter #false_signal #momentum_reversal #WLD
- **thesis_wrong** (EIGEN, $-92.93): Un segnale tsmom isolato (singola asset, singolo timeframe) su altcoin a bassa cap è insufficiente come tesi long: senza filtro di regime (es. BTC in uptrend, cross-asset momentum positivo) il segnale ha hit-rate basso e produce fade immediati — richiedere almeno N/M conferme multi-timeframe o escludere i long su altcoin quando il regime macro è neutro/bear. #tsmom #regime_filter #altcoin #false_positive #single_signal_risk
- **thesis_right** (ETH, $173.69): Un segnale tsmom=-1 confermato su timeframe orario è condizione sufficiente per uno short ATR-calibrated con R:R 2:1: il momentum bearish stabilito raggiunge il target nella sessione stessa senza riaggiustamenti. Nota di sistema: exit_px registrato (1680.57≈entry) è incoerente col PnL (+$173 corrisponde al target 1598.81) — il campo exit_px nel log di chiusura va validato contro il PnL, non assunto corretto. #tsmom #momentum-following #short #ETH #atr-stop #r2-target-hit #data-quality-warning
- **thesis_right** (BTC, $176.76): exit_px loggato (62347) è incongruente con target (59884) e PnL implicito (+176 USD ≈ Δ3.9%×qty): bug di serializzazione nello snapshot di chiusura. Per ogni strategia tsmom-follow, cross-checkare sistematicamente exit_px con pnl_usd/qty nel post-mortem; un prezzo di uscita corrotto nel journal produce slippage e Sharpe calcolati silenziosamente sbagliati, senza alert ovvio — aggiungere assertion exit_px coerente col segno del PnL in scripts/review.py. #tsmom-follow #BTC #data-integrity #logging-bug #target-hit #momentum-continuation
- **thesis_wrong** (basket, —): Ritirata da challenger: 20 trade paper, meanR -0.601 (perdente). Il paper trading ha falsificato l'edge. #lifecycle #retire #paper
- **thesis_wrong** (HYPE, $-90.24): TSMOM long signals on high-volatility speculative crypto (ATR% >1.5%) fire systematically near local exhaustion points where the run has already occurred; a regime filter (e.g., asset above HTF 20-period mean AND tsmom signal age <1 bar) is required to distinguish genuine continuation from crowded late entries. #tsmom #momentum_exhaustion #high_atr #crypto_speculative #regime_filter #entry_timing
- **thesis_wrong** (xyz:NATGAS, $-89.65): tsmom su commodity energetiche ad alta volatilità fondamentale (NATGAS) con segnale singolo (tsmom=1, nessuna confluence) è esposto a shock di evento (inventory report, meteo, flussi LNG) che invertono il momentum in poche ore prima che l'edge statistico possa materializzarsi; richiedere almeno un secondo segnale (es. regime bull confermato o funding positivo) o un filtro di volatilità implicita bassa prima di aprire long tsmom su NATGAS. #tsmom #natgas #energy #single-signal #fundamental-shock #no-confluence
- **thesis_right** (xyz:GOLD, $146.81): Segnali tsmom su asset macro (gold, commodità) tendono a esaurirsi in una singola sessione: un target ATR-calibrato a ~1.8x stop è sufficiente a catturare il follow-through senza overstare. Estendere il target oltre quella finestra espone al mean-reversion intraday, non a ulteriore momentum. #tsmom #macro #gold #atr-sizing #intraday-momentum #thesis_confirmed
- **execution_issue** (xyz:SPCX, $-85.90): Un segnale tsmom ha lookback multi-settimana ma lo stop ATR era abbastanza stretto da essere bruciato in 5 ore (~2× ATR giornaliero in mezza giornata). Il mismatch di scala temporale è la causa: per segnali slow-momentum, lo stop deve essere dimensionato sulla volatilità del periodo del segnale (es. ATR multi-day o percentuale fissa ≥ 2× ATR daily), altrimenti il rumore intra-day invalida posizioni la cui thesis potrebbe ancora essere valida sull'orizzonte corretto. #tsmom #timeframe_mismatch #stop_sizing #atr_calibration
- **thesis_right** (xyz:BRENTOIL, $151.60): tsmom in trend ribassista su commodity (Brent) genera alpha pulito quando il segnale è unidirezionale e il sizing ATR-calibrated è proporzionale alla volatilità: il trade ha raggiunto il target in ~30h senza toccare lo stop. Conferma che seguire il momentum meccanicamente senza override discrezionale è l'approccio corretto in regime di tendenza. #tsmom #commodity #brent #short #momentum #target_hit #mechanical
- **thesis_right** (cash:WTI, $163.88): tsmom su commodity energetiche con segnale confermato (-1) e R:R 2:1 tende a raggiungere il target entro 24-48h: non ampliare lo stop sulle reazioni intraday contro-trend e non uscire in anticipo — il regime momentum su WTI si esaurisce spesso dopo il primo impulso, quindi il full-target disciplinato batte il trailing speculativo. #tsmom #wti #energy #short #atr-stop #target-hit #commodity-momentum

## Eventi lifecycle

- **retire** (2026-06-23): 

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
