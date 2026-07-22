# AlphaZero Labs — trading research autonoma con agenti AI

Piattaforma di trading research che **impara in pubblico**: agenti LLM propongono trade con tesi falsificabili, li eseguono su un conto paper (balance fittizio, prezzi reali), scrivono post-mortem degli errori, e fanno evolvere le strategie di generazione in generazione. Il prodotto è la trasparenza: ogni tesi, errore e lezione è tracciata.

> **Stato: paper trading. Nessun fondo reale. Niente in questo repo è consulenza finanziaria.**

## Visione

- **Fase 1 (ora)**: validare il sistema — backtest onesti, paper trading live, learning loop dimostrabile
- **Prodotto 1**: "ricerca in pubblico" — journal tesi + lezioni + lineage evolutivo pubblici (stile Alpha Arena/nof1, ma continuo)
- **Prodotto 2** (ipotesi futura, non autorizzata): vault on-chain solo dopo evidenza verificata, track record plurimensile e approvazione umana separata

Design doc completo in Obsidian (`Projects/Active/AlphaZero Labs`).

## Architettura — due loop

```
INNER LOOP (tattico, ogni 4h)                 OUTER LOOP (evolutivo, giorni)
─────────────────────────────                 ──────────────────────────────
contesto live (prezzi/funding/OI/news)        strategia = artefatto YAML versionato
   → Analyst → debate bull/bear                  → LLM propone N mutazioni motivate
   → Strategist (tesi falsificabile)             → harness valuta su basket multi-asset
   → HARD LIMITS nel codice (insindacabili)      → walk-forward per fold e regime
   → Risk Manager LLM (approve/reduce/veto)      → selezione → challenger → paper
   → executor paper → stop/target reali          → campione paper → evidence gate
   → Reviewer post-mortem → LEZIONI
   → recall lezioni nei prompt  ←── il loop si chiude
```

Principi non negoziabili:
- **Tesi falsificabile obbligatoria** su ogni trade e ogni strategia
- **Blocco risk immutabile dall'LLM**: leva ≤2, rischio ≤1%/trade, stop obbligatorio, max 3 posizioni
- **Backtest solo su dati post-cutoff** del modello o forward test (lezione: FINSABER, Profit Mirage — i backtest LLM pubblicati sono contaminati)
- **Niente indicatori mainstream/lagging** (no SMA/RSI/MACD): solo segnali leading/strutturali da registry chiuso
- **Selezione multi-asset** (mean Sharpe su basket): mai promuovere su singolo asset
- **Paper status ≠ readiness**: DSR ≥0,95, holdout OOS e checker indipendente sono obbligatori; qualsiasi artefatto assente blocca
- **Publish fail-closed**: errori critici o health scaduta impediscono un nuovo deploy della dashboard
- **Coverage misurata**: ogni ticker dichiarato deve avere un prezzo HL fresco; listing con storico insufficiente restano visibili ma ineleggibili al ranking (warning, minimo 80% eleggibile). Le fonti di segnale obbligatorie come LIQIMB restano 9/9 fail-closed; ogni challenger Evolution L2 richiede inoltre il 100% dei segnali sul basket congelato prima di qualunque mutazione del paper state

## Componenti

| Path | Cosa fa |
|---|---|
| `scripts/fetch_universe.py` | Universo asset Hyperliquid (mainnet, volumi reali) filtrato per liquidità |
| `scripts/fetch_candles.py` | Candele 1h 12 mesi: Binance (crypto), yfinance (commodities/stock), HL fallback |
| `scripts/fetch_derivs.py` | Funding + taker flow storici (Binance fapi) |
| `scripts/fetch_edgar.py` | EPS trimestrali SEC EDGAR (XBRL, `filed` = point-in-time) per i 18 single-stock US su HIP-3 — zero vendor |
| `backtest/engine.py` | Exchange simulato: fill t+1 (anti-lookahead), fee, **funding storico** (opz.), **slippage size-aware** square-root (opz. `impact_k`), **liquidazione mark-to-market** su account equity (opz. `maintenance_margin_frac`), stop/target intrabar |
| `backtest/signals.py` | **Registry segnali** (chiuso, l'LLM compone ma non inventa codice) |
| `backtest/strategy.py` | Artefatto YAML → callback engine (rule AND/OR, direction, sizing) |
| `backtest/walkforward.py` | Metriche per fold temporali e regime bull/bear/chop |
| `backtest/evidence.py` | Verifica content-addressed di DSR, holdout OOS e receipt checker indipendente |
| `strategies/FORMAT.md` | Schema artefatto strategia (tesi, segnali, exit, risk immutabile, lineage) |
| `scripts/run_strategy.py` | Backtest singola strategia su un asset |
| `scripts/evolve.py` | Harness storico per mutazioni locali; non è schedulato nel paper runtime |
| `scripts/evolution_cloud.py` | Research OS L2: prereg approvata → mutazione portfolio one-shot → panel congelato → replay/checker → bundle per draft PR umana |
| `scripts/decide.py` | Pipeline agenti storica/API; non schedulata nel runtime cloud dal 12/07/2026 |
| `scripts/agents_paper.py` | Gestisce i desk storici; lo scheduler usa `--manage-only` e non apre nuove decisioni LLM |
| `scripts/claude_strategy.py` | Strategia ibrida: gate tsmom+liq_imbalance → PM LLM avverso |
| `scripts/glm_strategy.py` | **Strategia glm-5.2**: gate tsmom+xsection (ortogonale) + veto event/crowding → auditor LLM correlazione |
| `scripts/paper_trade.py` | Paper trading challenger segnale-based (cron) |
| `scripts/review.py` | Reviewer storico/API; le nuove review LLM passano da Codex con checker |
| `scripts/polymarket_paper.py` | **F7**: journal Polymarket storico; il cloud risolve le previsioni esistenti ma non ne genera di nuove |
| `scripts/propr_paper.py` | **F8**: challenge virtuale Propr; gate ufficiale invariato, più corsia `--manage-paper` sperimentale e paper-only con kill switch e account pin |
| `scripts/propr_guard.py` | Stop protettivi nativi server-side sul solo Free Trial autorizzato; default read-only, execute con doppio consenso |
| `scripts/runtime_health.py` | Manifest `paper/health.json`, validazione freshness e gate `publish_allowed` |
| `scripts/research_pack.py` | Census strict all-dex, shortlist candle bounded e contratti content-addressed Daily Maker/Hourly Checker L1 |
| `scripts/research_ops.py` | Backpressure, kill switch e clean streak 14 giorni dello stato operativo locale report-only |
| `prompts/research_os/` | Prompt e contratti GPT-5.6 per ricerca quotidiana source-first e review indipendente |
| `scripts/dashboard.py` | Dashboard statica — include evidence status e endpoint pubblico `/health.json` |
| `scripts/backtest_report.py` | Backtest basket multi-asset delle strategie attive → `paper/backtests.json` |
| `scripts/robustness_portfolio.py` | **Audit robustezza** edge portfolio: parameter stability + block bootstrap CI + true OOS (8m train / 4m test) |
| `scripts/voltarget_portfolio.py` | **Vol-target overlay** (Moreira-Muir): scala gross inverso a vol realizzata del book, abbatte la coda DD |
| `scripts/cron_run.sh` | Run unificato ogni 4h (crontab) |
| `pipeline/live.py` | Dati live: Hyperliquid/HIP-3, yfinance solo per posizioni legacy `xyz_*`, cache candle-only e pacing all-perps, OI e news RSS |
| `paper/*.jsonl` | Journal: trade, decisioni con tesi, lezioni — il "prodotto pubblico" |
| `db/schema.sql` | Schema Postgres/Supabase: trades, decisions, lessons (pgvector), equity_snapshots |
| `scripts/sync_supabase.py` | Sync incrementale journal→Supabase (idempotente via source_key, no-op senza credenziali) |

I dati storici (`data/`) non sono nel repo: si rigenerano con i 3 script fetch (~5 min).

## Registry segnali

| Segnale | Tipo | Asset | Note |
|---|---|---|---|
| `funding_percentile` | posizionamento | solo crypto | estremi di crowding |
| `taker_flow` | flusso aggressori | solo crypto | disponibile nei dataset storici Binance; non su HL live, quindi una spec che lo richiede viene bloccata dal source-coverage gate |
| `range_breakout` | struttura | tutti | rottura range con conferma volume |
| `vol_compression` | regime | tutti | setup pre-espansione |
| `tsmom` | momentum | tutti | Moskowitz-Ooi-Pedersen, orizzonti 7g+30g |
| `vwap_zscore` | estensione | tutti | deviazione dal VWAP rolling |
| `volume_surge` | partecipazione | tutti | percentile volume relativo |
| `xsection_momentum` | momentum relativo | tutti | rank nel basket (IC +0.089, t +21) |
| `nadaraya_watson` | struttura prezzo | tutti | envelope kernel-regression (DaviddTech); continuation IC +0.105 (t +5) |
| `earnings_window` | risk gate | stock xyz | veto vol attorno alla finestra earnings attesa (cadenza mediana filed EDGAR, causale). Non direzionale: PEAD falsificato |

**Random-control gate (08/07)**: l'ammissione via IC ora richiede anche il permutation
test (`ic_random_control` in `backtest/stats.py`): shuffle cross-section per data =
null hypothesis con stesso envelope statistico e zero informazione; soglia alpha_t ≥ 3.5
(Harvey-Liu-Zhu 2016, corregge il multiple testing). Un IC che passa il t-test vs zero ma
non batte il random è beta condiviso, non edge. Retro-test sui segnali cross-section
(12m): xsection momentum **alpha_t +19.2 → confirmed_alive**, funding carry
**alpha_t −7.2 → reversed** (= short-high-funding reale). Design da Vibe-Trading
`bench_runner_strict` (MIT). Caveat: vale per segnali cross-section; per i time-series
(tsmom, NW) serve un null diverso (time-shift circolare) — follow-up nel piano
integrazioni (Obsidian, Fase 2).

## Risultati finora (backtest 12 mesi, fee/slippage inclusi; paper live dal 11/06/2026)

**Campioni paper storici (non evidence-ready)**
- `xsmom-multihorizon-v1` — campione paper dal 06/07: 108 heartbeat/trade paper, basket_sharpe 0.818, DSR 0.7
- `xsmom-port-v1` — campione paper dal 07/07: 193 heartbeat/trade paper, basket_sharpe 0.427, DSR 0.91

Dal rilascio Integrity P0 il gate è hard e fail-closed: DSR ≥0,95, holdout OOS
`PASS`, hash coerenti e checker indipendente. Gli artefatti legacy non soddisfano
il contratto, quindi nessuna strategia corrente è evidence-ready.

**Hardening feed paper (18/07).** Il collector Coinalyze 1h usa ora l'open
interest come clock: le ore senza eventi di liquidazione sono barre esplicite a
zero, mentre l'assenza di OI resta un errore fail-closed. Il runner portfolio
acquisisce inoltre una sola snapshot mark Hyperliquid per run e la condivide con
tutti i child; un errore condiviso non innesca nuovi fetch nei child. I gate di
copertura prezzi 100% e LIQIMB 9/9 restano invariati.

**F8 — validazione storica su onchain prop firm (dal 09/07)**: `xsmom-multihorizon-v1`
ha prodotto uno storico su Propr (account Free Trial $5.000, capitale virtuale).
Il percorso ufficiale resta bloccato prima del client finché la strategia non supera
il contratto di evidenza. Dal 17/07 esiste inoltre una corsia sperimentale esplicitamente
autorizzata per il solo paper: `--manage-paper` richiede `PROPR_AUTOMANAGE_ENABLED=true`,
pin esatto `PROPR_EXPECTED_ACCOUNT_ID` e challenge `free-trial` attiva da $5.000.
Il runner verifica account e rischio ogni ora, aggiorna una tranche ogni 24h e non
riusa lo stato legacy alla prima attivazione. `propr_guard.py --execute` richiede il
secondo kill switch `PROPR_GUARD_ENABLED=true` e mantiene stop `stop_market`
reduce-only/close-position sul server Propr; `PROPR_GUARD_CANARY_ASSET` limita il
bootstrap a un asset (`*` = tutti). Questa eccezione non promuove la strategia,
non crea un candidato ufficiale e non abilita account paid o capitale reale.
Stato live e pass/fail sono pubblici sulla dashboard, sezione **Propr**.
Risk overlay Propr-aware nel runner (sera 09/07, da simulazione esatta challenge +
Monte Carlo bootstrap 1000 path): **gross 0.3** sizing fisso su balance iniziale
(a gross 1.0 breach daily-loss certo entro l'anno), **circuit breaker** giornaliero
(flat a -2% di giornata, breach 12m 6.4%→2.6%), **tranching** Jegadeesh-Titman
7 sub-book giornalieri (il reb168 monolitico è fragile alla fase del rebalance:
Sharpe 1.1-2.9 per sola scelta dell'ora; tranched 2.51 fase-invariante). Falsificati
con test: vol targeting sul book, ensemble con port-v1 (corr 0.82), universo ampio
PIT (edge diluito), inverse-vol legs, skip-24h, no-trade band, post-pass de-risk.
Attese oneste: pass ~90%, breach ~3.5%, pass mediano ~5 mesi.

**Evoluzione famiglia funding-squeeze (3 generazioni, crypto)**
| Strategia | Mean Sharpe (basket 9) | Esito |
|---|---|---|
| v1 breakout+funding | -1.04 (solo BTC) | baseline, perde nel chop |
| g2 fade del crowding | -0.43 | vince nel chop, travolto dai trend (SOL -15%) |
| g2-g1 +gate vol_compression | -0.13 | gate confermato |
| g2-g1-g2 (challenger) | -0.09, ret +0.03% | plateau → famiglia a breakeven, stop alle mutazioni (= overfitting) |

**TSMOM multi-asset** (BTC, ETH, SOL, GOLD, CL, BRENT, SILVER, SP500, MU)
- **Mean Sharpe 1.69, ret medio +11.3%, 8/9 asset positivi** — conferma la letteratura → challenger in paper

**Scoperta nuove strategie (sessione 26/06, ispirazione DaviddTech)** — basket 9 crypto, 12m walk-forward, fee/slippage inclusi, DSR vs champion:

| Strategia | Mean Sharpe | DSR | Ret | worstDD | Esito |
|---|---|---|---|---|---|
| **lux-flow-confluence** (champion tsmom+liq) | 0.71 | 0.87 | +11.0% | -22% | live edge di riferimento |
| **lux-nw-liq** (NW kernel + liq) | 0.59 | 0.87 | +9.6% | -24% | challenger competitivo: NW può sostituire tsmom |
| lux-nw-continuation (NW puro) | 0.18 | 0.33 | +2.2% | -25% | edge reale ma modesto standalone |
| lux-nw-tsmom (NW + tsmom) | -0.30 | 0.11 | -5.4% | -40% | **FALSIFICATA**: gambe correlate |
| lux-regime-3leg (champion + hmm gate) | 0.08 | 0.34 | +1.1% | -26% | **FALSIFICATA**: gate AND soffoca |

**Approfondimento 2° giro (26/06, tutto falsificato onestamente)** — validati prima via research IC, poi backtest:

| Idea | Edge misurato | Backtest | Esito |
|---|---|---|---|
| Pullback-in-trend (DaviddTech) | fwd ext +0.012 vs pull −0.007 | — | **FALSIFICATO**: il regime premia l'estensione, non il ritorno |
| Funding carry standalone | IC +0.094 ma t +1.6 (336h) | — | **FALSIFICATO**: edge troppo debole, non passa il gate |
| Efficiency Ratio (Kaufman) come gate | basket Δ ~0 (eterogeneo) | — | **FALSIFICATO**: valido su subset (BTC/ETH/SUI/ZEC), invertito su altri |
| Champion + xsection (3 gambe) | conditional IC TOP +0.032 vs BOT +0.015 | Sharpe −0.45/−0.75 | **FALSIFICATO**: edge reale ma richiede concordanza, non catturabile per-simbolo |

- **Lezione capitale**: l'edge cross-sectional (`xsection_momentum`, IC +0.089 t+21 — il piú forte mai misurato) **resta non sfruttato**. La cache era stale (201g vs 360g, ora rigenerata a 12m), e l'edge NON è catturabile nel motore per-simbolo (richiede concordanza direzionale). Abita nell'**engine a portafoglio dollar-neutral** (`xsmom-port-v1`, backtest +29% vs −20%, ritirata solo per strumentazione paper). É il filone prioritario da riprendere.
- **La cura del regime filter**: l'implementazione DaviddTech corretta è un **VETO** sui periodi chop (sospende), non una terza gamba AND (soffoca). Lezione documentata in `paper/lessons.jsonl`.

**🏆 FILONE PRINCIPALE RIAPERTO (26/06): cross-sectional momentum a PORTAFOGLIO.**
`xsmom-port-v1` ripresa in produzione. L'edge cross-sectional (`xsection_momentum`, IC +0.089 t+21 — il piu' forte misurato) non era sfruttato perche': (a) la cache era stale a 201g vs 360g candele (rigenerata a 12m); (b) l'edge NON e' catturabile nel motore per-simbolo (falsificato: Sharpe -0.27/-0.45/-0.75 su 3 varianti — richiede concordanza, non attività). Abita nell'**engine a portafoglio dollar-neutral**. Backtest basket 9 crypto, 12m walk-forward, fee+slippage inclusi:

| Config | Ret | Sharpe | maxDD | DSR | vs benchmark |
|---|---|---|---|---|---|
| **xs-mom dollar-neutral lb168 reb168 g1** | **+79.8%** | **2.11** | **-19%** | 0.91 | benchmark equal-weight **-8.8%** (maxDD -59%) |
| xs-mom dollar-neutral lb168 reb24 g1 | +94.7% | 2.34 | -17% | 0.94 | ribilanciamento +frequente |
| xs-mom long-only lb168 reb168 g1 | +72.7% | 1.08 | **-65%** | 0.62 | senza netting → DD 3x peggio |

Il dollar-neutral e' cruciale (abbatte il DD del 46pp). Era stata ritirata il 25/06 **solo per strumentazione paper** (logga `rebalance`/`heartbeat` con equity, non `open`/`close` → appariva con 0 trade). Fix: `paper_stats` deriva ora Sharpe/ret/maxDD dall'equity curve per `engine:portfolio`. Runner ripristinato in `cron_run.sh` e `paper-run.yml`.

**Sweep edge portfolio ortogonali (26/06, 8 configurazioni testate)** — cercavo un secondo edge forte, onestamente non c'e':

| Config | Sharpe | maxDD | Verdetto |
|---|---|---|---|
| **xsmom** (core) | **2.11** | -19% | l'unico davvero forte |
| **xsmom-multihorizon** (lb 96+168+336) | 1.85 | **-16%** | compagno conservativo, DD minore |
| funding carry book | 0.39-0.77 | -24/39% | debole, NON esplode a portfolio |
| TSMOM long vol-target | 1.01 | **-68%** | drawdown inaccettabile |
| xsmom vol-weighted | 1.05 | -23% | peggio dell'equal-weight |
| xsmom+tsmom-long combo | 1.80 | -33% | DD peggiore, niente vantaggio |

**Loop per-simbolo SVUOTATO (26/06)** — tutte le strategie per-simbolo erano rumore colorato (Sharpe 0.12-0.71 vs xsmom 2.11). Ritirate lux-flow-confluence, lux-nw-liq, lux-confluence-rr2. Il loop e' ora **tutto engine:portfolio**: xsmom-port (core) + xsmom-multihorizon (conservative). Le desk LLM (agents-v1: 54% win realizzato su 13 trade) restano per il track record live dimostrativo.

**Espansione cross-asset FALSIFICATA (26/06)** — cercavo un secondo edge diversificando il basket (crypto corr 0.63 = troppo comuni). Due vie provate, entrambe fallite:
- Book unico crypto+commodities: IC degrada (+0.089 → +0.023). Il cross-sectional richiede asset **correlati** (fattore da nettare); crypto+commodities corr~0 mischia dinamiche non comparabili.
- Book commodities separato dollar-neutral: IC +0.057 sembrava un edge, MA a portafoglio **−33%** vs B&H long-only **+49%**. In un super-ciclo rialzista uniforme, il market-neutral fallisce (la gamba short perde sistematicamente).

**Conclusione: xsmom crypto e' il nostro UNICO edge forte.** Cercare un secondo edge portfolio con questi dati/regime e' diminishing returns evidente (8 fattori + cross-asset testati, tutti falsificati). Il gate reale verso M5 (vault on-chain) e' ora il **track record paper nel tempo**, non altra ricerca.

**🏆 SECONDO EDGE FORTE TROVATO: HIGH-VOL anomaly (26/06, factor zoo).** Cercavo fattori ortogonali mai testati come book. Lo zoo a 8 fattori ha falsificato quasi tutto (reversal, low-vol, TSMOM-neutral, flow, OI, top-trader), MA con un trucco diagnostico: i fattori con Sharpe NEGATIVO forte sono segnali *invertiti*. Invertito, **HIGH-VOL** (long asset piu' volatili del basket / short i calmi) e' un edge reale e ortogonale:

| Strategia | Sharpe | maxDD | DSR | corr vs xsmom |
|---|---|---|---|---|
| xsmom (core) | 2.13 | -19% | 0.79 | — |
| **highvol-port** | **2.32** | -22% | 0.87 | **+0.28** |
| **xsmom-highvol-combo** (70/30) | **2.38** | **-16%** | **0.88** | diversifica |

Il risk premium crypto: long alt volatili (SOL/CRV/ZEC) / short blue chip calmi (BTC/ETH). Correlazione solo +0.28 con xsmom → diversificazione **genuina** (le varianti xsmom erano corr ~0.9). La combo 70/30 ha il **minor drawdown del progetto (-16%)** a Sharpe piu' alto (2.38). Tre strategie in produzione.

- **Segnale nuovo validato**: `nadaraya_watson` (envelope kernel-regression, firma DaviddTech). Edge study (`scripts/research_nw.py`): il breakout di banda è un segnale di **continuation** (IC +0.105, t +5 a 48h), non di mean-reversion (il fade ha IC negativo → falsificato, coerente col regime trend 2026-H1).
- **Lezione chiave di falsificazione**: la confluence funziona solo fra gambe **ortogonali** per costruzione (prezzo-struttura NW × flusso liq → competitivo; prezzo-struttura NW × momentum tsmom → correlate, l'AND ammazza le entry). E un gate di regime come AND a 3 gambe soffoca l'edge; andrebbe usato come **veto** sui periodi chop, non come requisito di entry.

**🔬 AUDIT DI ROBUSTEZZA (26/06, `scripts/robustness_portfolio.py`).** Tre test onesti sui 3 edge portfolio prima di dichiararli "reali": (1) parameter stability (sweep lookback/rebalance), (2) block bootstrap 95% CI sul Sharpe (preserva autocorr del ribilanciamento), (3) true OOS (calibra param sui primi 8m, freeze, test sui 4m finali mai visti).

| Strategia | Sharpe full | CI95 inf | OOS-freeze | Stabilità | Giudizio |
|---|---|---|---|---|---|
| **highvol** | 2.32 | 0.37 | **3.78** | **100%** | il piu' affidabile: altopiano largo + OOS eccellente |
| **xsmom** | 2.13 | -0.16 | **-0.79** | 33% | reale ma FRAGILE: il config scelto generalizza (OOS 2.29), MA la selezione ingenua best-su-train overfitta (lb240/reb48 Sharpe 3.53 → OOS -0.79). Mai ri-calibrare i parametri su finestre corte |
| **combo 70/30** | 2.62 | 0.43 | **3.05** (DD -9.6%) | — | best risk-adjusted; bootstrap DD: coda 5% avversa -25.5%, solo 6% prob di DD peggiore di -25% |

Verdetto onesto: **nessuno passa il gate rigoroso CI95-inf > 1.0** — NON perche' gli edge siano falsi, ma perche' **12 mesi (~50 ribilanci settimanali) sono fondamentalmente insufficienti per inchiodare uno Sharpe** (CI larghi ±2). highvol e' il piu' robusto in superficie; xsmom e' reale ma peaky e sensibile all'overfitting da selezione. La combo ha il profilo migliore e il DD genuinamente basso. **Trovata**: il blend-ratio sweep mostra w_xs=0.50 marginalmente migliore del 70/30 scelto (Sharpe 2.75 vs 2.62, stesso maxDD -15.8%) — altopiano robusto, 50/50 e' un'alternativa valida. **Caveat giallo**: l'OOS (ultimi 4m) ha Sharpe PIU' ALTO dell'in-sample → test window breve e probabilmente regime-favorvole (non leggere 3.x come attesa realistica). **Conclusione capitale**: la certezza statistica non si compra con piu' backtest sugli stessi dati — serve TEMPO (track record forward out-of-sample). Questo conferma che il gate verso M5 e' di **tempo, non di codice**. Le strategie sono **promettenti ma non ancora provate**.

**🛡 VOL-TARGET OVERLAY (26/06, `scripts/voltarget_portfolio.py`).** Il bootstrap della combo mostrava coda avversa DD al 5° percentile = -23.2% (3% prob di drawdown peggiore di -25%) — il rischio di rovina reale e' la CODA, non lo Sharpe. Overlay Moreira-Muir ("Volatility-Managed Portfolios" 2017): scala il gross `m = clip(σ*/σ_realized, 0.3, 1.5)` dove σ_realized e' la vol annualizzata del **book stesso** sui rendimenti passati (rolling 720h, anti-lookahead). Funziona perche' la vol clusterizza (GARCH): i rendimenti avversi si concentrano nei periodi ad alta vol, quindi de-riskare li' abbatte la coda.

| Config combo 50/50 | Sharpe | maxDD | coda5% DD | P(DD<-25%) |
|---|---|---|---|---|
| **OFF (baseline)** | 2.75 | -15.8% | -23.2% | 3% |
| **σ\*=20% overlay** | 2.68 | **-11.3%** | **-17.9%** | **0%** |

Costo Sharpe **nullo** (-0.06), maxDD -4.5pp, coda avversa **+5.3pp**, **rovina eliminata** (P(DD<-25%) 3%→0%). Gradiente monotono pulito (σ\*=20/25/30% → coda -17.9/-22/-25.9%) = non overfit a un punto fortunato. avg_gross 0.72-0.78 (de-risk ~25% medio), moltiplicatore min 0.34 nei periodi turbolenti. La firma (costo Sharpe minuscolo + riduzione DD materiale nella coda) e' esattamente cio' che Moreira-Muir documentano come vol-targeting reale. Sweet spot σ\*=20-25%. **Caveat onesto**: σ*/vol_window/floor-cap sono nuovi parametri selezionati sui dati, ma il risultato e' robusto sull'intervallo e floor/cap non sono binding.

**✅ CABLATO IN PRODUZIONE (26/06 sera).** L'overlay e' ora attivo nel paper engine live (`portfolio_paper.py`): `_vol_target_multiplier` calcola `m=clip(target/realized, floor, cap)` dalla vol realizzata DEL BOOK sui returns tra heartbeat (cron 4h, annualizzo √2190); `equity_history` append-only nel `state.json` (trim 720 punti ~120g), anti-lookahead; warmup `m=1.0` finche' non ci sono abbastossi punti. Il candidato `xsmom-highvol-voltarget-v1.yaml` gira in cron locale + workflow cloud (glob `*voltarget-v1.yaml`). Regression test `test_vol_target_overlay_multiplier`. Ora puo' accumulare track record reale (il vero gate M5).

**Onestà del backtest (funding storico + slippage size-aware).** Il funding è ora storico reale per-asset (la costante legacy sovrastimava di ~8x e nascondeva i flip di segno nei mesi bear). Lo slippage è opzionalmente un modello square-root (Almgren 2005, additivo sul base). Slippage size-aware (square-root, Almgren 2005) e liquidazione mark-to-market su account equity (con MMR) opt-in. Su CRV (illiquido) l'impact smaschera un Profit Mirage: Sharpe 0.73→0.16 a $10k. Su BTC (liquido) l'edge regge fino a $10M AUM (1.37→1.33). La liquidazione MTM coincide col legacy a leva ragionevole (≤5, nessuna posizione attiva la rischia) ma a leva 8 + flash crash lascia il margine residuo realistico (1088$ vs 0 del legacy rigido). `run_strategy.py --impact 0.5 --mmr 0.01` per attivarli.

**🔬 Alpha Zoo sweep FALSIFICATO (08/07, Fase 2 piano integrazioni).** Vendorizzati 456
fattori equity MIT da Vibe-Trading (`vendor/vibe_zoo/`: alpha101 Kakushadze, gtja191,
qlib158, academic). Protocollo pre-registrato (`scripts/research_zoo.py` +
`research_zoo_backtest.py`): IC + random-control (159 con |alpha_t|≥3.5, 81 sotto gate
overlap ≤0.4 vs xsmom/highvol) → backtest portfolio dollar-neutral dei top-3 mutuamente
diversi, fee+slippage. Esito: **Sharpe 2.3-3.0 e OOS positivo, MA DSR 0.25-0.50 << 0.95
con K=456** — indistinguibili dal massimo del rumore su 456 prove. Nessuna promozione;
lezione in lessons.jsonl. Due conferme di metodo: (1) l'alpha_t su fwd 7d overlappato si
inflaziona sui segnali persistenti (cluster volume/vol = size-beta di regime); (2) il DSR
è la difesa reale contro il factor mining. xsmom + highvol restano gli unici edge.

**🔬 PEAD/SUE su HIP-3 FALSIFICATO (08/07, Fase 6).** Edge study earnings sull'universo
stock HIP-3 (`scripts/research_pead.py`): 323 eventi su 15 mega-cap US (2018-2026), EPS
EDGAR point-in-time (`filed`), entry t+1, ritorni market-adjusted. IC ≈ 0 su fwd 5/20/60g,
alpha_t max −1.1 (tutto `noise`), anche su ultimi 3 anni. Coerente con la letteratura: il
drift post-earnings è arbitraggiato via sulle large-cap liquide (sopravvive nelle small-cap,
che HIP-3 non lista). Salvage: il calendario filing è ora il **veto `earnings_window`**
(risk gate non direzionale, stesso precedente di `news_event`). Pipeline dati:
`fetch_edgar.py` — SEC gratis, niente vendor (financialdatasets: free tier morto, resta
in panchina per delisted/estimates a $20 se mai servisse).

**Tesi falsificate** (documentate in `paper/lessons.jsonl`): scalp-exit su crowding, flow-confirmed breakout, fade VWAP (7/7 asset), stop più stretti dell'invalidazione. Pattern: il regime 2026-H1 premia il trend, punisce il mean-reversion.

**Learning loop dimostrato**: ZEC long (tesi squeeze) → stop -50.92$ (=0.5% budgettato, il reduce del Risk Manager ha dimezzato il danno) → 2 lezioni → recall attivo nei prompt.

## Come gira

```bash
uv sync                                          # dipendenze
uv run scripts/fetch_universe.py && uv run scripts/fetch_candles.py && uv run scripts/fetch_derivs.py
uv run scripts/run_strategy.py strategies/tsmom-v1.yaml BTC 6   # backtest
uv run scripts/decide.py BTC,ETH,SOL --pack      # genera il context pack per Codex
uv run scripts/dashboard.py && open dashboard/index.html
sh scripts/cron_run.sh                           # run completo (in crontab ogni 4h)
```

**Operazioni LLM di execution** — dal 12/07/2026 passano da **Codex/GPT-5.6** autenticato
con la subscription ChatGPT. Salvo le eccezioni Research OS L1/L2 delimitate sotto,
i workflow di execution e il cron locale non ricevono credenziali Z.ai/OpenRouter e
non generano decisioni, review, mutazioni o nuove previsioni Polymarket. Il cloud resta attivo per dati, strategie meccaniche,
uscite, scoring, sincronizzazione e dashboard. La subscription Codex non è una
API: `scripts/llm.py` resta nel repository come backend HTTP storico/testabile,
ma è dormiente nei workflow schedulati. Il kill switch
`LLM_RUNTIME_DISABLED=1` impedisce chiamate accidentali anche se il Mac conserva
vecchie chiavi provider in `.env`; il valore predefinito è disabilitato.

Capacità conservate nel layer HTTP storico:
- **Effort differenziato per ruolo** — Strategist/Analyst/evolve a `max` thinking; Bull/Bear/Risk/Auditor a `low`/`medium` (sono veto, non serve 32k token) → risparmio ~60% token a parità di decisioni.
- **Structured output nativo** — i ruoli con `schema` (strategist/risk/auditor/…) rispondono via Anthropic tool use forzato → JSON già validato, niente parsing regex fragile.
- **Self-consistency** — la decisione finale dello Strategist è il majority vote di N=3 campioni (`GLM_SC_N`), riduce la varianza del flip-di-moneta di una singola chiamata LLM.
- **Cache applicativo** (`GLM_CACHE_DIR`) — memoizza per hash(prompt): eval deterministici, dedup, test a costo zero.

Ogni nuova proposta LLM di execution viene quindi prodotta come artefatto Codex,
verificata da un checker indipendente e soltanto dopo può essere ammessa al paper trading.
Nessuna chiave della subscription viene copiata nel repository o in Actions.

Il **Research OS L1** è la prima eccezione cloud delimitata: Cloudflare schedula
`research-maker.yml` alle 07:15 Europe/Rome e `research-checker.yml` ogni ora;
GitHub Actions usa Z.AI come primario sull'endpoint API generale con web search e
JSON validato. Solo sugli errori di quota/autorizzazione Z.AI (incluso `429` code
`1113`) usa il fallback OpenRouter `deepseek/deepseek-v4-pro`, sempre con web
search e la stessa validazione di provenance. Pack e receipt restano artefatti GitHub per 30 giorni,
mai commit. Il Maker censisce via metadata tutti i perp core/HIP-3, arricchisce
al massimo 20 mercati core 24/7 e produce 5–8 famiglie source-first; il Checker
revisiona soltanto il nuovo hash. Al massimo una famiglia arriva a
`PREREG_REVIEW_ONLY`; `NO_CANDIDATE` è valido. Nessun output L1 può creare una
strategy spec, aprire P&L/holdout o modificare paper state e journal.

Una receipt `APPROVE_PREREG_ONLY` può alimentare il **Research OS L2** event-driven.
L2 mantiene una coda FIFO transazionale e usa esclusivamente
`deepseek/deepseek-v4-pro` via OpenRouter in due job separati: un Maker one-shot e un
Checker che ripete il panel congelato. I retry riusano gli artifact autorevoli e non
generano altre mutazioni. Sono ammesse solo portfolio già supportate (`xsmom`, `tsmom`,
`highvol`); nuovi dati, eventi, order flow, BBO/L2, engine o codice producono `BLOCKED`.
Actions è read-only sul repo e genera al massimo un bundle `HUMAN_PR_REQUIRED`: push,
draft PR e merge restano azioni Codex/umane autenticate. Tutti i gate statistici e
semantici devono passare prima che il registry paper possa vedere il challenger.
Dettagli in `docs/evolution-pipeline.md`.
Il Worker non espone endpoint HTTP di dispatch: le esecuzioni manuali passano
solo da `workflow_dispatch` autenticato nell'interfaccia o API di GitHub.

## Roadmap

Stato reale: M1–M4 costruiti. Prima di qualsiasi ipotesi su fondi reali servono
evidenza riproducibile, track record plurimensile, affidabilità operativa e un gate umano separato.

- [x] M1 — dati, harness, registry, formato strategia, loop evolutivo (3 generazioni)
- [x] M2 — paper trading live; execution LLM resta fuori dal runtime deterministico, Research OS L1 è report-only e L2 produce bundle paper-only one-shot con DeepSeek V4 Pro, replay indipendente e PR umana
- [x] COT report CFTC (posizionamento commodities = analogo del funding)
- [x] Champion/challenger per-trade con gate formale (**deflated Sharpe ≥0.95**); i portfolio non sono auto-promovibili perché gli heartbeat non sono trade indipendenti
- [x] Integrity P0 — maker/checker evidence contract, runtime health fail-closed, endpoint pubblico e CI mirata
- [x] Journal → Supabase (schema + `sync_supabase.py` idempotente + workflow cloud gated; il recall semantico pgvector è cablato, l'embedding da popolare a progetto creato)
- [x] Interfaccia v2 → Cloudflare Pages (`lux-ai.pages.dev`, deploy nel workflow)
- [x] M4 — testnet Hyperliquid (`execute_testnet.py` dry-run sicuro, isolato per regola #2 — va in cron solo con `HL_API_SECRET` configurato)
- [ ] **M5 — vault HyperEVM** (ERC-4626, solo a track record paper dimostrato su mesi). Gate di tempo, non di codice.

**Cosa manca a M5**: mesi di edge paper robusto, receipt OOS indipendenti, SLO operativi,
policy di rischio/custodia e approvazioni legali e umane. `promote.py` decide soltanto
il lifecycle paper/evidence; non autorizza capitale.

### Hardening & audit (25/06)
Suite di test verde (**98 pass**). Sessione di audit + bugfix:
- **Integrità del journal (finding chiave)** — i test `*_time_stop_fallback` chiamavano `open_from_decision` → `log_event` scriveva aperture **false** (`thesis:"t"`) sul journal REALE `paper/journal.jsonl`, e il cron le committeva. Bug cronico: ogni `pytest` corrompeva il "prodotto pubblico". Fix: monkeypatch del `JOURNAL` verso `tmp_path` + pulizia di 6 righe false già committate.
- **`agents_paper.py`**: floor difensivo `time_stop_h or 96` (bug latente simmetrico al desk geo: un LLM che emette `time_stop_h=0` faceva scattare l'uscita a *ogni* candela chiusa). Aggiunto test di regressione.
- **`backtest_report.py`**: `pd.Timestamp.utcnow()` deprecato in pandas → `Timestamp.now(tz="UTC")` (rottura imminente al prossimo upgrade).
- **`cron_run.sh`**: leftover strutturale (riga indentata copia-incollata dal blocco YAML del workflow cloud) + prima chiamata `agents_paper.py` senza `|| true` (un errore interrompeva tutta la catena locale).
- **Cleanup lint**: import inutilizzati, variabili morte, `NameError` latente (`notional` non definito in `test_impact.py`) risolti. `ruff --select F` pulito.
- `.gitignore`: tooling temporaneo di live-render/screenshot del design skill (`scripts/_render_*.js`, `scripts/_shot_*.png`).

### Audit a 4 assi & remediation (02–03/07)
Code review completa (motore backtest · layer decisionale/evolutivo · pipeline/infra/security · dashboard) → **79 finding**. Tutti i tecnici chiusi, **148 test verdi**.

- **7 CRITICAL** (commit `24d1811`/`4b556ea`): `is_portfolio` dallo spec engine, non dagli heartbeat (root cause del doppio win-rate e delle ritirazioni su numeri gonfiati); `equity_dd_pct` dal peak, non vs capitale iniziale; `ask_glm` al posto di `ask_claude` (loop evolutivo morto da settimane per ImportError mascherato); XSS escaping su tutti i campi LLM/journal nella dashboard; deploy `*.html` completo (non solo index); self-heal chiavi posizione non canoniche; persist state su ogni fill (niente PnL doppio sui partial).
- **HIGH/MEDIUM** (commit `25b297a`/`10ff58e`/`a4fb921`/`6ccc5a9`/`3ec0218`): lookahead 24h su segnali daily Coinalyze rimosso; niente riapertura post-stop sullo stesso segnale persistente; `bars_per_year` osservata (Sharpe non piú gonfiato 2.3× su commodities); costi validazione e DSR `N_TRIALS` dal grid reale; upsert chunked+retry per Supabase; scritture atomiche degli storici; **majority vote** con maggioranza vera + symbol canonicalizzato; liquidazione legacy 1/leva disattivata con MMR; `size_multiplier` clampato [0,1]; 429 ritentato; `sanitize_headline` anti prompt-injection sui titoli RSS; `basket_sharpe_r` con epsilon+clamp; self-consistency N=3 sul desk geopolitics; pairing reviewer close→open cronologico.
- **Security/infra**: rotazione dei due token esposti (**GH_PAT** + **CLOUDFLARE_API_TOKEN**); GitHub Actions e clone Kronos pinnati a SHA, wrangler a versione esatta; **RLS abilitato** sulle 4 tabelle Supabase del vault (erano in `public` senza RLS); rimossi i bypass sperimentali (`HARD_LIMITS_BYPASS`, `bypass_limits`) → limiti hard di nuovo attivi su tutti i desk.

Rapporto integrale + log operativo nel vault dedicato (`AlphaZero Labs Vault/`).

### Dashboard UX per non-tecnici (06/07)
Implementati 8 dei 12 punti dell'audit UI/UX (`dashboard/IMPROVEMENTS.md`, spuntati lì):
- **Digest "Cosa è successo oggi"** — 2-3 frasi in italiano piano generate dall'LLM a ogni run sui fatti del giorno (aperture/chiusure, best/worst della settimana, lezione recente); errore LLM → la build prosegue senza digest.
- **Nav a 2 livelli** — da 13 voci tecniche a 4 gruppi (Oggi · Strategie · Diario · Contesto) con riga secondaria del gruppo attivo; mobile 375px ok.
- **Nomi amichevoli ovunque** — `friendly_label()` + mappa `labels` nel data: albero evolutivo, lifecycle, backtest e legenda mostrano il nome, l'id tecnico vive nel tooltip.
- **Equity aggregata senza spaghetti** — default top 3 + peggiori 3, le altre curve si accendono dalla legenda.
- **Benchmark & verdetto** — rendimento assoluto del sistema e confronto con l'S&P 500 sullo stesso capitale, entrambi in dollari e percentuale, più lo scarto dal benchmark.
- **Card conti compatte** (riga + sparkline, chart lazy all'apertura), **glossario inline** (tooltip su dollar-neutral, drawdown, sharpe…), **timestamp relativi**, **tooltip badge feed**.
- **Albero evolutivo orizzontale** (07/07) — una card per famiglia con contatore ("12 generazioni · 4 attive · 8 ritirate"), collapse nativo (le famiglie tutte ritirate partono chiuse), nodi pill colorati per status, dentro la famiglia resta solo la generazione (g2.g1…), dettagli nel tooltip.

Rimasti: test su device fisico (10), dominio custom (12).

## Riferimenti

[TradingAgents](https://github.com/TauricResearch/TradingAgents) (pattern, non i numeri) · [Kronos](https://github.com/shiyu-coder/Kronos) · [FINSABER](https://arxiv.org/abs/2505.07078) · [Profit Mirage](https://arxiv.org/abs/2510.07920) · [TSMOM](https://quantpedia.com/strategies/time-series-momentum-effect) · [nof1 Alpha Arena](https://nof1.ai/)
