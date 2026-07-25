# commodities-trend-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **created**: 2026-06-13
- **family**: commodities-trend

## Tesi

I trend sulle commodities sono persistenti (driver macro/COT, cicli lunghi). Un book dedicato alle sole commodities con TSMOM dovrebbe essere più pulito del basket misto. Falsificata se non batte buy-and-hold risk-adjusted sulle commodities a 6 mesi.

## Note evoluzione

seed di ricerca

## Performance (paper)

- equity: $9,241.85
- trade chiusi: 21 · win rate: 29%
- PnL totale: $-686.44
- posizioni aperte ora: 0

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| xyz_CL | stopped | 69.48713951090214 | $-103.73 |
| xyz_BRENTOIL | stopped | 72.96856288587512 | $-103.92 |
| xyz_CL | stopped | 69.98142398471336 | $-104.77 |
| xyz_BRENTOIL | stopped | 73.27285364518785 | $-104.81 |
| xyz_BRENTOIL | stopped | 74.68142183486911 | $-100.70 |
| xyz_CL | stopped | 71.18857507691278 | $-100.25 |
| xyz_CL | stopped | 73.06142460265451 | $-97.32 |
| xyz_GOLD | stopped | 4091.185697122655 | $-97.74 |
| xyz_GOLD | stopped | 4136.6855209165005 | $-96.32 |
| xyz_SILVER | stopped | 60.25856648962934 | $-95.08 |
| xyz_SILVER | target | 58.31728282355859 | $157.54 |
| xyz_SILVER | target | 57.33857159823299 | $160.42 |
| xyz_SILVER | stopped | 58.684997935977506 | $-96.38 |
| xyz_GOLD | stopped | 4061.685349530347 | $-97.20 |
| xyz_SILVER | stopped | 59.34499503220596 | $-95.81 |
| xyz_SILVER | target | 57.49057212839042 | $158.28 |
| xyz_GOLD | target | 4017.708460943441 | $155.08 |
| xyz_SILVER | target | 55.938281410278364 | $161.24 |
| xyz_GOLD | stopped | 4029.428514883121 | $-101.32 |
| xyz_SILVER | stopped | 57.01357041232819 | $-97.70 |
| xyz_GOLD | retired | 4007.0 | $14.05 |

## Lezioni

- **thesis_wrong** (basket, —): Specializzazione per asset-class: TSMOM sulle SOLE commodities (Sharpe 0.43) NON batte buy-and-hold (-0.70 vs B&H) — nel periodo le commodities sono semplicemente salite, holding vince. Il basket MISTO resta superiore: la diversificazione cross-asset del trend-following e' parte dell'edge, non un dettaglio. crypto-trend-flow batte il B&H crypto ma con Sharpe assoluto debole (0.33). #research #asset-class #diversification #falsificazione
- **luck** (xyz_CL, $-103.73): Nei sistemi TSMOM su commodity (CL), quando il segnale fires ma il trade non va mai in favore (hi_water = entry) e viene stopped entro ~1 sessione, è un whipsaw tipico di regime di transizione/chop. La tesi momentum non era sbagliata in sé — il segnale era coerente col setup — ma il timing era cattivo: il momentum era già esausto o in inversione. **Lezione actionable**: quando ATR% è bassa (<1%) e il segnale TSMOM fires contro una struttura di prezzo che mostra già decelerazione (range tightening o gap fill), considerare un filtro di regime (es. richiedere conferma di breakout di range o attendere 1-2 bar di follow-through prima di entrare) per ridurre i whipsaw che costano ~2x ATR per nulla. L'esecuzione (stop 2x ATR, target 3.6x ATR, R/R 1.8:1) era adeguata e non va modificata — il problema è l'entry timing, non il risk management. #tsmom #whipsaw #crude-oil #low-atr #regime-transition #momentum-exhaustion #entry-timing
- **execution_issue** (xyz_BRENTOIL, $-103.92): I trade momentum su commodity ad alta volatilita' (Brent) con stop a ~2x ATR vengono fermati dal noise di breve termine prima che il trend si sviluppi. Per tsmom su commodity energeiche serve stop >= 2.5-3x ATR (o filtro di regime di vol): con 2x ATR su Brent il rischio di whipsaw intra-sessione e' troppo alto, e il trade esce per volatilita' non per tesi sbagliata. #tsmom #brent #stop-tight #whipsaw #execution
- **execution_issue** (xyz_CL, $-104.77): Per un segnale tsmol su CL con ATR% 0.46, uno stop a ~2x ATR (0.93%) è troppo tight per un trade di trend-following intraday: il rumore mean-reverting dello stesso giorno può fermare il trade prima che la componente direzionale abbia tempo di esprimersi. Nei fade-trend su commodity volatili come CL, usare almeno 2.5–3x ATR come stop (oppure un time-stop di fine sessione) riduce il rischio di essere whipsawati dal noise intraday pur mantenendo R/R accettabile (target qui era 1.67% = ~3.6x ATR, quindi con stop a 3x ATR il R/R restava >1.2). #tsmom #crude-oil #stop-too-tight #atr-multiple #intraday-whipsaw #execution-vs-thesis
- **execution_issue** (xyz_BRENTOIL, $-104.81): I segnali tsmom generati in regime di volatilità compressa (ATR% < 0.5%) catturano spesso rumore intraday anziché trend reale: la direzione del move che ha innescato il segnale è troppo piccola per avere significato predittivo, e il prezzo tende a mean-revert entro 1-2 ATR. In questi regimi, o il filtro richiede un breakout di entità minima proporzionale all'ATR (es. price deve essere ≥3-4 ATR dal recente close-range), o si amplia il filtro temporale (tsmom su timeframe daily anziché hourly). Il risultati è che lo stop a 2×ATR viene hit in 2 ore, il che indica che il segnale non aveva enough trend momentum per sostenersi neppure transitoriamente. #tsmom #low_volatility_regime #brent #stop_too_tight_for_noise #commodities #signal_filtering #mean_reversion_vs_momentum #intrabar_volatility
- **execution_issue** (xyz_BRENTOIL, $-100.70): Per strategie tsmom su commodities (Brent, WTI), un stop a 2× ATR con entrata intraday espone al cosiddetto 'stop farming': il normale back-and-forth di sessione scatterà lo stop prima che il trend possa esprimersi. Soluzione: allargare il stop a 3–3.5× ATR (o usare una struttura a tempo: se entro N ore il prezzo non ha mosso almeno 0.5R a favore, chiudere manualmente) per dare al segnale multi-giorno lo spazio minimo per sopravvivere al noise intraday. #tsmom #brent-oil #stop-too-tight #intraday-vs-multiday-mismatch #execution #commodities #stop-farming
- **execution_issue** (xyz_CL, $-100.25): Per entrate tsmom a market su commodity ad alta volatilità come CL, uno stop a 2x ATR è troppo tight: il rumore intraday stoppa il trade prima che il trend possa esprimersi. Soluzioni: (a) allargare lo stop a 2.5–3x ATR mantenendo lo stesso target per non degradare il win-rate, oppure (b) inserire un filtro di entrata (es. attesa di un close sotto un livello recente o un pullback) per ridurre la probabilità di entrare proprio nel noise spike. Un tsmom system con stop < 2.5 ATR su CL produrrà troppi falsi stop-out che erodono il drift positivo del segnale. #tsmom #crude_oil #stop_sizing #atr_filter #execution #trend_following #intraday_noise
- **thesis_wrong** (xyz_CL, $-97.32): I segnali tsmom in commodities entrati in controtrend immediato (stop hit entro 1 sessione con stop a 2x ATR) indicano che il momentum era già esausto al momento dell'entry. Per i follow:tsmom short su CL, un filtro di conferma — ad esempio richiedere che il prezzo chiuda almeno 1 ATR sotto l'ultimo swing high prima di entrare, o scartare segnali generati dopo >3 bar di trend già maturo — riduce significativamente le probabilità di entrare proprio sul punto di reversal. Senza conferma di break, il tsmom nudo cattura troppi falsi segnali in zone di esaurimento. #tsmom #crude-oil #momentum-exhaustion #entry-confirmation #commodities #stop-2x-atr #counter-trend-reversal
- **execution_issue** (xyz_GOLD, $-97.74): Per segnali tsmom intraday su oro, uno stop a ~2x ATR (1.16% vs ATR 0.58%) è troppo stretto: l'oro genera spike contro-trend che spazzano regolarmente 2x ATR entro poche ore. I fade/trend-short su gold richiedono stop ≥3x ATR o un time-stop che prevenga l'esposizione al noise intraday puro — altrimenti la win rate crolla per micro-volatilità e non per difetto di tesi. #gold #tsmom #stop-too-tight #atr-sizing #intraday-noise #commodities-trend-v1
- **execution_issue** (xyz_GOLD, $-96.32): In strategie tsmom su GOLD, uno stop a ~2x ATR (1.25% vs ATR 0.62%) è troppo tight: l'oro ha rumore intraday che routine-mout supera 2 ATR anche in trend direzionale, causando stop-out per mean-reversion anche quando il momentum signal è corretto. Per tsmom su commodity con ATR% bassa ma coda grassa come gold, usare stop ≥ 3x ATR o pattern-based (swing high recente) per evitare il 'chop-out' che distrugge il hit-rate e l'aspettativa del segnale. #tsmom #gold #stop-to-tight #atr-multiple #commodities-trend-v1 #noise-vs-signal #execution
- **luck** (xyz_SILVER, $-95.08): In commodity altamente volatili come l'argento, i segnali tsmom a freq giornaliera sono esposti al whipsaw in regime di compressione/espansione di volatilità: il prezzo può invertire 2x ATR in una singola sessione annullando il segnale momentum senza che la tesi direzionale fosse necessariamente sbagliata. Quando il VIX-commodities o l'ATR% stesso è in fase di espansione rapida (come qui ATR 1.23% ma stop a 2x), il filtro di regime deve richiedere conferma multi-leg (es. tsmom + breakout chiusura) prima di entrare su metallo volatile, oppure allargare lo stop a 2.5-3x ATR per evitare di essere scippati dal normale rumore intraday di silver. #tsmom #silver #whipsaw #commodities #momentum #stop-placement
- **thesis_wrong** (basket, —): Ritirata da challenger: 20 trade paper, basket_meanR -0.561 (perdente su media per-asset). Il paper trading ha falsificato l'edge. #lifecycle #retire #paper

## Eventi lifecycle

- **retire** (2026-07-20): basket_mean_r_negative

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
