# lux-flow-confluence-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **parent**: [[lux-confluence-rr2-v1]]
- **created**: 2026-06-25

## Tesi

lux-confluence-rr2-v1 usava una confluence a 3 gambe (tsmom + liq_imbalance + kronos_forecast), ma kronos_forecast e' stato FALSIFICATO come segnale direzionale il 14/06 (Sharpe -0.2/-0.3 standalone, dimezza lo Sharpe come gate). La gamba kronos era quindi MORTA ma ancora cablata in AND: bloccava entrate valide e rumoreggiava con forecast senza alpha. Questa strategia la RIMUOVE: confluence a 2 gambe (tsmom + liq_imbalance), entrambe validate e ortogonali — tsmom = edge di prezzo (Moskowitz, 58 futures), liq_imbalance = unico segnale di flusso forzato sopravvissuto a TUTTE le falsificazioni del progetto (funding, OI, news direzionale, mean-reversion: tutti falsificati; liq resta). Backtest basket 9-asset 6m (validazione pre-deploy, 25/06): Rimuovere kronos MIGLIORA ogni metrica — Sharpe +0.25 -> +1.26, DSR 0.58 -> 0.81, 6/9 -> 9/9 simboli positivi, worstDD -35% -> -22%. La gamba morta dragava il parent. Exit RR2 + stop ATR (validati 21-22/06: RR2 su entry ad alta convinzione TP-itta piu' spesso di RR3; ATR-stop anti noise-stop). Falsificata se: in paper non batte il parent lux-confluence-rr2-v1 su PnL realizzato (il kronos poteva avere valore come gate di rischio non testato), O se liq_imbalance perde la cache Coinalyze (degrada a neutro -> nessuna entry).

## Note evoluzione

v1 seed: confluence 2-gambe (tsmom + liq_imbalance), rimuove la gamba kronos del parent falsificata come direzionale. Mutazioni: soglia liq extreme_pct, lookback liq, RR 1.8-2.5, aggiunta di smart_money_ratio come eventuale terza gamba ortogonale (se mostra IC nel research).

## Performance (paper)

- equity: $9,913.03
- trade chiusi: 6 · win rate: 33%
- PnL totale: $-81.56
- posizioni aperte ora: 0

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| BTC | retired | 59557.0 | $-2.94 |
| XRP | retired | 1.0361 | $-5.27 |
| ZEC | retired | 404.83 | $-15.83 |
| ETH | retired | 1559.0 | $4.73 |
| SOL | retired | 70.446 | $-67.20 |
| CRV | retired | 0.19189 | $4.95 |

## Lezioni

- **execution_issue** (BTC, $-2.94): Quando due segnali di momentum/flow (tsmom + liq_imbalance) entrano in confluence su BTC ma il prezzo non produce follow-through entro ~1 sessione (23h), i segnali stavano confermando un move già esaurito piuttosto che anticiparne uno nuovo. Il retirement/scratch è stato la scelta corretta, ma il punto debole è l'entry: senza un freshness gate sul tempo intercorso tra la prima occorrenza del segnale e l'ingresso, si rischia di vendere il minimo già scontato. Lezione: nei fade/momentum confluence su asset ad alta liquidità come BTC, aggiungere un filtro di "staleness" — se l'ATR% non è cambiato di almeno 0.5x dalla generazione del segnale originale, l'edge è decayed e il trade va skippato. #confluence_staleness #tsmom #btc #scratch_management #entry_timing #signal_decay #momentum
- **execution_issue** (XRP, $-5.27): In regimi di ATR compressa (low-vol squeeze), la confluenza di N segnali momentum/flow non genera follow-through perché manca il carburante (vol realizzata). Filtra i signal-vote con un floor su ATR percentile o richiedi un breakout-trigger (es. close sotto struttura recente) prima di attivare l'ingresso: la confluenza senza volatilità è rumore, non edge. #confluence-without-volatility #atr-filter #time-stop #tsmom #liq_imbalance #xrp #low-follow-through #entry-timing #signal_vote
- **execution_issue** (ZEC, $-15.83): Per una tesi tsmom (time-series momentum) il time-stop "retired" a 23h con solo lo 0.9% di move avverso è incoerente: il tsmom è intrinsecamente un segnale di persistence multi-giorno (3-7 giorni tipici), quindi chiudere per retire prima che il prezzo abbia testato almeno 1 ATR (≈2% qui) contro la direzione significa sistematicamente impedire al fattore di esprimersi. In regime dove ATR_pct ≈ 2%, un fade/trend short aperto a -1σ dal proprio stop non deve essere ritirato prima di 48-72h o di un'inversione del segnale tsmom stesso. Sintesi: allinea la durata minima del trade all'orizzonte del fattore guida della tesi. #tsmom-time-horizon-mismatch #time-stop-vs-thesis-horizon #zec #retired-too-early #lux-flow-confluence-v1 #atr-aware-exit
- **execution_issue** (ETH, $4.73): In regimi low-ATR, quando un segnale confluence ha un'attesa di vita di ore (es. tsmom+liq_imbalance retired in <24h), stop e target calibrati su multipli ATR multi-day (3-6x) sono strutturalmente incompatibili con la durata del segnale: il trade viene ritirato prima che il prezzo possa muoversi di una frazione significativa del range aspettato. Soluzione: legare stop e time-stop alla *stessa metrica* — se il segnale ha half-life di N ore, il time-stop deve forzare l'uscita prima che il move aspettato diventi inferiore ai costi di transazione, e il size deve riflettere quel range effettivo, non l'ATR daily. Alternativamente, filtrare i segnali in low-vol richiedendo un'intensità di confluensa maggiore per giustificare hold times più lunghi. #signal-lifetime-mismatch #low-vol-regime #risk-frame-vs-signal-duration #scratch-trade #time-stop-discipline #lux-flow-confluence-v1
- **execution_issue** (SOL, $-67.20): When two backward-looking signals (tsmom + liq_imbalance) agree on direction, they are NOT independent confluence — they reflect the same recent price/flow history and will fail simultaneously at inflection points. Real confluence requires orthogonal signal dimensions (e.g., momentum + on-chain structure + sentiment). Additionally, a time-stop must be calibrated to the ATR-based stop distance: retiring a trade at 14h when the stop is set at 3 ATR creates a structural inconsistency where the position is closed in the worst zone (loss booked, thesis untested, protection unused). Rule: time-stop should be proportional to stop distance/ATR ratio, not arbitrary wall-clock. #confluence-illusion #backward-looking-signals #time-stop-vs-atr-stop-mismatch #retired-exit #lux-flow-confluence-v1
- **execution_issue** (CRV, $4.95): I segnali tsmom con ATR% < 2.5% e nessun follow-through nelle prime 6-8h sono candidati a retirement immediato, non a time-stop da 14h: il momentum che non parte subito in regime di bassa volatilità è quasi sempre un segnale tardivo (late entry), non un setup che ha bisogno di più tempo. Pre-filtrare le entry tsmom su un threshold minimo di ATR% (o richiedere conferma di price-action nella prima ora) riduce drasticamente il capital impiegato in trade flat che restituiscono ~0R. #tsmom #low_volatility_regime #late_signal #time_stop #retirement #R_multiplo_negligible #no_follow_through

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
