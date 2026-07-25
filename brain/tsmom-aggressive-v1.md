# tsmom-aggressive-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **created**: 2026-06-13
- **family**: tsmom-aggressive

## Tesi

Profilo aggressivo sullo stesso edge TSMOM: leva 2x, stop largo, target esteso, più posizioni. Tesi: lasciar correre i trend con stop larghi cattura le code dei movimenti. Falsificata se il drawdown extra non è compensato dal rendimento (Sharpe non superiore a tsmom-v1).

## Note evoluzione

seed di ricerca

## Performance (paper)

- equity: $8,684.77
- trade chiusi: 16 · win rate: 19%
- PnL totale: $-1,252.32
- posizioni aperte ora: 0

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| xyz_MU | time_stop | 1004.3990555908204 | $123.74 |
| xyz_CL | stopped | 69.48713951090214 | $-155.56 |
| xyz_BRENTOIL | stopped | 73.34428003393238 | $-157.74 |
| xyz_MU | stopped | 952.776873161245 | $-151.28 |
| xyz_BRENTOIL | stopped | 74.68142183486911 | $-152.26 |
| xyz_CL | stopped | 71.18857507691278 | $-151.62 |
| xyz_CL | stopped | 73.06142460265451 | $-145.55 |
| xyz_GOLD | stopped | 4091.185697122655 | $-145.34 |
| xyz_GOLD | stopped | 4136.6855209165005 | $-142.45 |
| xyz_SILVER | stopped | 60.25856648962934 | $-141.42 |
| xyz_GOLD | stopped | 4061.685349530347 | $-139.73 |
| xyz_SILVER | stopped | 59.99928261676966 | $-135.74 |
| BTC | retired | 63927.0 | $85.82 |
| ETH | retired | 1861.2 | $169.85 |
| xyz_SP500 | retired | 7509.22998046875 | $-10.99 |
| xyz_MU | retired | 930.239990234375 | $-2.05 |

## Lezioni

- **thesis_right** (xyz_MU, $123.74): In un time-series-momentum trade dove l'asset realizza ~50% del target in 4 giorni e poi stalla, il time-stop è preferibile al 'hope-and-hold': il momentum residuo si sta esaurendo anche se il segnale non è ancora flippato. La regola generale: in tsmom-aggressive, se dopo N barre il prezzo è entrato in una zona di stallo (< 30% del range target-stop avanzato per barra), chiudi al time-stop piuttosto che aspettare il target — il drift momentum ha una mezza-vita e stargli seduto sopra significa finanziare il mean-reversion degli altri. #tsmom #time_stop #momentum_decay #execution #partial_winner #MU
- **execution_issue** (xyz_CL, $-155.56): Negli short tsmom su asset ad alta volatilità rumorosa come CL, uno stop a ~2x ATR è insufficiente: il rumore intraday sopra una media mobile può fermare il trade prima che il trend riprenda. Per tsmom su CL usare stop >= 2.5-3x ATR, o entrare con conferma (chiusura sotto il livello di breakdown) invece che a market sul signal crossover, per ridurre la probabilità di essere stopped sul primo rimbalzo. #tsmom #crude-oil #stop-sizing #noise-filter #entry-confirmation
- **execution_issue** (xyz_BRENTOIL, $-157.74): Per strategie tsmom aggressive su commodity volatili come Brent, uno stop a 2x ATR genera stop-out per puro noise intraday. Richiede almeno 2.5–3x ATR o un filtro di conferma post-entry (es. chiusura H4 oltre livello di stop) per evitare whipsaw che erodono il capitale anche quando il momentum signal è corretto. #tsmom #brent-oil #stop-too-tight #whipsaw #atr-sizing #commodity-volatility #execution
- **execution_issue** (xyz_MU, $-151.28): Per strategie tsmom-aggressive su strumenti con ATR% ≥ 2.5%, uno stop a ~1.8 ATR è troppo esposto al noise intraday: il segnale momentum può catturare uno spike locale che si mean-reverte entro poche ore. Soluzione: o ampliare lo stop a ≥2.5 ATR (accettando un size più piccolo per mantenere il rischio costante), o aggiungere un filtro di non-entrata quando il prezzo è già extended >2 ATR dalla VWAP/session mean, per evitare di comprare al locale high subito prima di un revert. #tsmom #stop-too-tight #high-atr #whipsaw #execution #momentum-fade
- **execution_issue** (xyz_BRENTOIL, $-152.26): In TSMOM aggressivo su commodity energetiche con ATR% compressa (<0.8%), uno stop a 2x ATR è statisticamente troppo stretto rispetto al micro-noise intraday del crude oil: il regime low-vol non offre abbastanza trend-persistence per giustificare l'ingresso, e il primo mean-reversion spike batte lo stop. Aggiungere un filtro di regime (ATR% rank o vol-ratio vs storico) che disabiliti il segnale TSMOM quando la volatilità è nel bottom decile, oppure allargare il stop a 3x ATR in regime low-vol, riduce il tasso di whipsaw senza degradare il R:R atteso. #tsmom #brent-oil #low-vol-regime #stop-too-tight #whipsaw #execution #atr-filter #regime-filter
- **execution_issue** (xyz_CL, $-151.62): Per strategie tsmom aggressive su strumenti ad alta volatilità (CL), evitare ingressi nei primi 30-60 minuti dell'apertura sessione US (~14:00 UTC): il rumore di prezzo in quella finestra viola sistematicamente stop a 2 ATR anche quando il segnale momentum è corretto. Aggiungere un filtro di sessione (o posticipare l'entry di 1h) riduce i falsi stop-out senza degradare il fattore di profitto dei trade che funzionano. #tsmom #crude-oil #session-timing #stop-whipsaw #execution-filter #aggressive-variant
- **luck** (xyz_CL, $-145.55): In regime di ATR basso (≤1% su CL), i segnali tsmom hanno un signal-to-noise ratio peggiore e uno stop a 2x ATR si traduce in una distanza assoluta talmente stretta (~1.6%) che il normale rumore intraday di una sessione è sufficiente a farti uscire prima che il momentum abbia modo di svilupparsi. Quando ATR% è sotto soglia, ampliare il stop a 2.5–3x ATR (o ridurre size proporzionalmente per mantenere lo stesso rischio in USD) evita di essere stopped dal noise di sessione su un trade dove la tesi direzionale può ancora essere corretta. #tsmom #low_volatility_regime #stop_sizing #crude_oil #atr_multiple #noise_vs_signal #risk_per_trade
- **luck** (xyz_GOLD, $-145.34): I segnali TSMOM intraday su oro richiedono stop di almeno 2.5–3×ATR o un filtro di conferma multi-bar: con ATR ~0.58% e noise band tipica del 1%+ intraday, uno stop a 2×ATR (~1.2%) è dentro la zona di fluttuazione statistica e viene triggherato dal rumore prima che il momentum si esprima. #tsmom #gold #intraday-whipsaw #stop-sizing #atr-multiplier #noise-band #aggressive-variant
- **execution_issue** (xyz_GOLD, $-142.45): Per strategie tsmom su GOLD intraday, uno stop a ~2x ATR (1.25% in questo caso) è insufficiente a filtrare il rumore naturale dell'asset: l'oro produce facilmente spike di 2–3 ATR in finestre di 12–15h puramente da flusso di ordini (es. London open, auction). Risultato: il ~60% dei trade viene fermato su noise prima che la componente direzionale del segnale possa esprimersi. Un filtro pratico: richiedere almeno 2.5–3x ATR di stop per tsmom su GOLD, oppure aggiungere un time-gate che ignora segnali generati in finestre di bassa liquidità (post-US-close) dove il momentum signal è più suscettibile a mean-reversion nella sessione successiva. #tsmom #gold #stop-too-tight #atr-filter #intraday-noise #session-timing
- **execution_issue** (xyz_SILVER, $-141.42): In commodity ad alta volatilità come l'argento, uno stop a 2x ATR (variant 'aggressive') è vulnerabile al whipsaw intraday: il trade è stato fermato in sole 24h con un move contro del 2.45%, perfettamente in linea con il rumore normale dello strumento. Per TSMOM su asset con ATR% > 1%, il filtro minimo dovrebbe essere stop ≥ 3x ATR oppure richiedere conferma multipla (es. breakout + chiusura sotto) prima di entrare, pena un tasso di false-signal incontrollabile che erode il PnL anche quando la direzione di fondo è corretta. #tsmom #silver #stop-too-tight #whipsaw #high-volatility-commodity #2x-atr #aggressive-variant
- **thesis_wrong** (basket, —): Ritirata da challenger: drawdown equity -16.55% (soglia -15.0%), 12 trade chiusi. Perdita grave precoce — l'edge è falsificato dal capitale a rischio. #lifecycle #retire #paper #drawdown

## Eventi lifecycle

- **retire** (2026-07-14): drawdown_breach

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
