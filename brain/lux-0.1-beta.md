# lux-0.1-beta

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **parent**: [[tsmom-liq-v1]]
- **created**: 2026-06-17
- **family**: lux-0.1-beta

## Tesi

LUX 0.1 BETA — la flagship: distillazione del meglio appreso finora. Entra solo su TRIPLA CONFLUENZA ORTOGONALE — trend (tsmom) + liquidazioni reali Coinalyze (liq_imbalance, l'unico edge robusto provato) + forecast del foundation model Kronos. Tre fonti indipendenti (prezzo, flusso liquidazioni, modello) che devono concordare → entry rare ma ad altissima convinzione. La direzione esce dal VOTO di 5 segnali ortogonali (ai tre si aggiungono smart-money positioning e OI-confirmed trend). Veto sugli eventi news (tone falsificato come predittore — usato solo come filtro di volatilità). Exit lesson-informed: stop alla soglia di invalidazione, vincenti a 3R. Rischio: leva 3x, 2% per trade (esposizione effettiva ~0.8x via rischio/stop), 3 posizioni. Gira in parallelo al desk agenti LLM (LUX-aware: ragiona sulla stessa confluenza) e ne condivide il pool di lezioni. Falsificata se: la confluenza a 5 segnali NON batte il tsmom-liq a 2 segnali sullo Sharpe_r in paper → i segnali extra sono rumore e va semplificata.

## Note evoluzione

LUX 0.1 BETA — tripla confluenza ortogonale (tsmom+liq+kronos), voto a 5 segnali, veto news. Flagship unica.

## Performance (paper)

- equity: $10,263.47
- trade chiusi: 19 · win rate: 21%
- PnL totale: $-665.18
- posizioni aperte ora: 0

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| NEAR | stopped | 2.0992724160290996 | $-205.16 |
| WLD | stopped | 0.60095097596196 | $-200.80 |
| WLD | target | 0.65110597395576 | $569.70 |
| NEAR | stopped | 2.1561149137554 | $-196.61 |
| WLD | stopped | 0.6267007249319699 | $-208.09 |
| WLD | stopped | 0.62494572500217 | $-199.71 |
| ETH | stopped | 1748.7524300498997 | $-195.48 |
| WLD | target | 0.65076197396952 | $566.18 |
| WLD | stopped | 0.62354172505833 | $-202.86 |
| ZEC | stopped | 456.39148174433996 | $-195.55 |
| SUI | stopped | 0.72376272104949 | $-196.55 |
| ZEC | stopped | 448.63648205453995 | $-190.52 |
| ETH | stopped | 1718.8274312469002 | $-190.58 |
| NEAR | stopped | 2.0655374173784997 | $-195.54 |
| WLD | stopped | 0.60856572565737 | $-190.58 |
| WLD | stopped | 0.5980357260785699 | $-174.51 |
| WLD | stopped | 0.58304022667839 | $-170.81 |
| ZEC | target | 410.65373357384993 | $517.58 |
| CRV | target | 0.19777424208903 | $594.71 |

## Lezioni

- **execution_issue** (NEAR, $-205.16): In un sistema multi-segnale che mescola segnali reattivi (tsmom, liq_imbalance) e segnali predittivi (kronos_forecast), la piena confluenza deve essere unanime sui predittivi: kronos_forecast=-1 su un long indica che il modello forward-looking aveva già scontato un calo, mentre tsmom e liq_imbalance riflettono solo il passato recente. Aprire con 2/3 positivi quando il forecast è contrario degrada il setup da 'signal_vote' a 'majority vote' — categoria con edge storicamente inferiore. Regola generale: i segnali predittivi funzionano da veto, non da voto paritario; se forecast != direction, il trade non si apre indipendentemente dalla confluenza dei reattivi. #signal_conflict #forecast_veto #prediction_vs_reaction #kronos #execution #near #signal_vote_logic
- **thesis_wrong** (WLD, $-200.80): tsmom + liq_imbalance senza conferma di smart_money_ratio e oi_trend identificano squilibri di book retail, non flusso direzionale sostenuto: il prezzo raggiunge lo stop prima che il momentum si materializzi perché manca il capitale istituzionale che tiene il bid. Per long su altcoin ad alta volatilità intraday, richiedere almeno uno dei segnali 'smart' (oi_trend o smart_money_ratio = 1) come gating condition, oppure ridurre la size proporzionalmente all'assenza di conferma OI. #signal_confluence #smart_money_gap #liq_imbalance_trap #altcoin_long #gating_condition
- **thesis_right** (WLD, $569.70): Quando il signal_vote è 3/3 su segnali primari (tsmom+liq_imbalance+kronos_forecast) ma smart_money_ratio e oi_trend rimangono a zero, il trade produce un impulso rapido e concentrato — la risoluzione avviene in minuti, non ore. Senza conferma di flusso istituzionale l'estensione oltre il primo terzo del range è improbabile: impostare tp1 al 40-50% del range entry→target con frac 0.5 per catturare il core del P&L prima che il momentum si esaurisca. #signal_vote_3of3 #no_institutional_flow #fast_resolution #tp1_missing #momentum_crypto #lux-0.1-beta
- **execution_issue** (NEAR, $-196.61): Quando un segnale forward-looking (kronos_forecast=-1) contraddice i segnali backward-looking (tsmom=1, liq_imbalance=1), il modello predittivo deve avere potere di veto sull'entry: momentum e liq_imbalance descrivono ciò che è già accaduto, il forecast cattura la direzione attesa — senza consensus sul segnale predittivo la regola corretta è no-trade, non majority-vote tra segnali asimmetrici per natura. #signal_conflict #kronos_veto #forward_vs_backward_looking #consensus_required #lux-0.1-beta
- **thesis_wrong** (WLD, $-208.09): Quando tsmom + liq_imbalance + kronos_forecast convergono long ma smart_money_ratio=0 e oi_trend=0, il segnale è probabile falso positivo su altcoin: il momentum retail senza conferma istituzionale (flusso smart money, crescita OI) identifica un micro-bounce da liquidità e non l'inizio di un trend. Richiedere almeno uno tra smart_money_ratio=1 o oi_trend=1 come gate obbligatorio per i long su asset a bassa capitalizzazione. #altcoin #false-momentum #smart-money-divergence #signal-gate #lux-0.1-beta
- **execution_issue** (WLD, $-199.71): Stop a 1.27× ATR (2.5% con atr_pct=1.97%) cade dentro il rumore intraday dei crypto: non è una barriera di invalidazione, è una zona di rumore casuale. Regola generale: se smart_money_ratio=0 (nessuna conferma istituzionale), il floor minimo di stop sale a 2× ATR oppure il trade non si apre — momentum+liq_imbalance senza flow istituzionale hanno edge ridotto e richiedono più respiro o size dimezzata per sopravvivere alla volatilità normale. #stop_undersized_vs_atr #smart_money_absent #crypto_noise_floor #position_sizing #momentum_long
- **execution_issue** (ETH, $-195.48): In sistemi multi-segnale a voto di maggioranza, il segnale predittivo (kronos_forecast) deve funzionare da veto gate, non da terzo voto ponderato: quando forecast=+1 (bullish) e la maggioranza current-state vota short, l'entrata avviene contro l'unico segnale che modella il movimento futuro — il prezzo conferma il forecast entro 2h. Regola operativa: forecast in disaccordo con direction → skip entry o sizing ridotto al 25% finché forecast non si allinea. #signal_conflict #forecast_veto_gate #majority_vote_flaw #entry_filter #lux-0.1-beta
- **thesis_right** (WLD, $566.18): Con confluenza 3/3 su (tsmom + liq_imbalance + kronos_forecast), un oi_trend contrarian isolato e non confermato da smart_money_ratio è rumore, non veto: la confluence momentum-liquidità-forecast domina la divergenza OI singola in regime direzionale. Usare oi_trend come segnale di veto solo se allineato con smart_money_ratio ≥ 1. #signal_confluence #oi_divergence_noise #liq_imbalance #tsmom #kronos_forecast #momentum_regime #target_hit
- **thesis_wrong** (WLD, $-202.86): Quando tsmom+liq_imbalance votano long ma oi_trend è -1 (OI calante), il movimento è verosimilmente ricopertura di short o distribuzione, non accumulo genuino: la tesi mancava di un gate obbligatorio su OI. Regola generale: su long momentum in altcoin, oi_trend < 0 deve bloccare il trade o dimezzare la size, perché senza flusso 'nuovo' lo stop è quasi sempre raggiunto prima del target. #oi_divergence #momentum_without_oi_confirmation #altcoin_long #signal_gate_missing
- **execution_issue** (ZEC, $-195.55): In un sistema multi-segnale con voto di maggioranza, tsmom controcorrente rispetto alla direzione del trade (tsmom=-1 su long) non è un voto in minoranza ma un veto strutturale: l'anchor di momentum codifica il regime sottostante e un 2/3 che lo ignora genera entrate anti-regime ad alta frequenza di stop. Regola generale: se sign(tsmom) != sign(trade_direction), il segnale non si apre indipendentemente dagli altri vote — il majority override dell'anchor di momentum è una fonte di perdita sistematica, non una diversificazione del segnale. Nota: close.ts (11:00) precede opened_at (12:00) — terza occorrenza del bug look-ahead intra-barra (cfr. lessons NEAR jun-15, GOLD jun-15): il PnL è inaffidabile e il fix min_hold_bars>=1 non è stato implementato. #tsmom_veto #signal_contradiction #vote_override #anti_regime_entry #hard_veto #timestamp_inversion #look_ahead_bug #recurring_unfixed
- **execution_issue** (SUI, $-196.55): Quando tutti i segnali primari concordano (vote unanime) ma l'asset ha ATR giornaliero > 3%, lo stop fisso al 2.5% viene mangiato dal rumore prima che la tesi possa dispiegarsi: calibrare lo stop a 1.5–2× ATR dell'asset specifico, non a una percentuale flat uguale per tutti i simboli. #stop_sizing #atr_calibration #high_vol_l1 #signal_consensus #noise_vs_signal
- **execution_issue** (ZEC, $-190.52): Con tsmom=-1 il sistema ha aperto un long contraddicendo la propria tesi (AND logico): liq_imbalance+kronos_forecast senza momentum confermante non bastano per fade contro-trend — richiedere agreement completo (tsmom>=0) o alzare la soglia di voto a 3/3 quando il momentum è contrario alla direzione. #signal_conflict #tsmom_override #entry_filter #counter_momentum_fade #vote_threshold
- **thesis_wrong** (ETH, $-190.58): Quando tsmom=-1 (momentum ribassista confermato), i segnali liq_imbalance e kronos_forecast non sono sufficienti a giustificare un long: il vote system ha permesso l'apertura contro il segnale dominante. Regola generale: tsmom deve essere gate obbligatorio (hard filter, non voto) per le posizioni long — se tsmom<0 la trade non si apre, indipendentemente dal punteggio aggregato degli altri segnali. #signal_conflict #tsmom_gate_missing #counter_trend_disguised #vote_system_failure #momentum_dominance
- **execution_issue** (NEAR, $-195.54): Quando exit_px è favorevole alla direzione ma pnl è negativo, e ts_close (22:00) precede ts_open (23:00), il pipeline ha un bug di race condition o ordinamento eventi: ogni close deve superare due sanity-check prima di essere accettato come valido — (1) ts_close > ts_open, (2) sign(exit_px - entry_px) coerente con direction e sign(pnl). Senza questi guard, una chiusura fantasma può spendere 195 USD di equity su un trade che non è ancora aperto. #execution_issue #pipeline_bug #timestamp_ordering #pnl_sanity_check #data_integrity
- **execution_issue** (WLD, $-190.58): Quando oi_trend=-1 su un long momentum (OI cala mentre il prezzo sale), il rally è alimentato da short-covering o thin liquidity, non da nuovi compratori: la tesi '3 segnali bullish' è strutturalmente indebolita. Regola generale: oi_trend negativo deve azzerare o dimezzare il size su momentum-long, indipendentemente dal voto complessivo dei segnali — la divergenza OI/prezzo precede inversioni rapide, non sfortuna. #oi_divergence #momentum_long #signal_weighting #position_sizing #short_covering_trap
- **execution_issue** (WLD, $-174.51): Quando liq_imbalance contraddice la direzione (qui -1 su un long), il segnale di flusso real-time deve fungere da veto hard sull'aggregazione a voti: tsmom e kronos_forecast sono indicatori ritardati/predittivi, liq_imbalance è pressione istantanea dell'order book. Un sistema a maggioranza 2:1 che ignora il segnale di flusso genera adverse selection sistematica — si entra while distribution is active, si viene stoppati sul primo soffio contro senza espansione di range. Regola generale: liq_imbalance in direzione opposta blocca l'ingresso finché non si allinea, oppure riduce la size a ≤30% del normale. #signal_conflict #liq_imbalance_veto #adverse_selection #voting_logic #entry_filter
- **execution_issue** (WLD, $-170.81): Quando liq_imbalance è contrario alla direzione del trade (qui -1 su long con vote 2/3), la stop-distance ATR-calibrata al 2.5% è strutturalmente insufficiente in sessioni a bassa liquidità (02:00–06:00 UTC): lo slippage reale è stato ~5% (exit 0.583 vs stop pianificato 0.598), il doppio del rischio atteso. Regola: conflitto esplicito su liq_imbalance → dimezzare il size OPPURE allargare lo stop a ≥2× ATR prima dell'apertura della sessione; mai usare ATR-stop fisso quando un segnale di liquidità avverso è già presente nell'entry signal. #signal_conflict #liq_imbalance #gap_risk #stop_slippage #low_liquidity_session #size_reduction
- **thesis_wrong** (basket, —): Ritirata da challenger: drawdown equity -18.48% (soglia -15.0%), 15 trade chiusi. Perdita grave precoce — l'edge è falsificato dal capitale a rischio. #lifecycle #retire #paper #drawdown
- **thesis_right** (ZEC, $517.58): Quando tsmom e liq_imbalance convergono short ma kronos_forecast dissente (1 su 3 contrario), il consensus 2/3 è sufficiente se il segnale momentum è strutturale: il dissenso di kronos indica incertezza di timing, non invalidazione della tesi. Stop stretto al 2.5% ATR ha protetto il trade nella fase iniziale e il target è stato raggiunto in <30h — esecuzione size/stop/target coerente con la volatilità del sottostante. #tsmom #liq_imbalance #signal_consensus #short #ZEC #target_hit #execution_ok
- **thesis_right** (CRV, $594.71): Quando tsmom + liq_imbalance + kronos_forecast convergono tutti a -1 su un asset DeFi ad alta volatilità, il momentum ribassista è robusto abbastanza da reggere fino al target pieno (~7.4% move in 4 giorni): non chiudere prima su rumore intraday. #tsmom #liq_imbalance #kronos_forecast #short #defi #signal_confluence #target_hit

## Eventi lifecycle

- **retire** (2026-06-23): drawdown_breach

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
