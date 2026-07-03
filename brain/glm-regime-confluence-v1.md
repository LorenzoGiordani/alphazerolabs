# glm-regime-confluence-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **created**: 2026-06-24

## Tesi

Strategia ibrida progettata da glm-5.2 su delega di Lorenzo, informata dalle lezioni accumulate del progetto (166 lezioni, 8 segnali falsificati). 1. GATE ORTOGONALE: due lenti momentum indipendenti concordano — tsmom (trend
   assoluto, Moskowitz) + xsection_momentum (forza relativa nel basket, market-
   neutral, netta il beta). Confluenza assoluto+relativo = il move non e' solo
   drift di mercato, e' alpha relativo confermato. Ortogonali a lux-confluence
   (tsmom+liq+kronos) e claude-strategy (tsmom+liq).
2. VETO DI REGIME/EVENTO: news_event attivo (volatilita event-risk, il tono e
   falsificato ma la vol no) O kronos_vol alta (regime imprevedibile) O
   funding_percentile estremo CONTRO direzione (crowding headwind).
3. VOTE DI CONVINZIONE: hmm_regime(trending) + taker_flow + smart_money_ratio +
   oi_trend. Ogni allineamento +1 al conviction score (0-4).
4. LLM AUDITOR DI PORTAFOGLIO: non oracolo, non predittore di prezzo (lezione
   dura: forecast LLM = niente alpha). Giudica SOLO rischio di correlazione col
   book aperto e freschezza. Una chiamata, solo se il gate ha candidati.
5. EXIT ROBUSTA: stop ATR 2x (floor 1x), RR2, time_stop 96h.
FIX 25/06 (rotta dalla nascita, 0 trade in 18 run): il gate AND a 2 gambe era SEMPRE chiuso perche' la cache xsection_momentum (data/xsection/) non era committata ne' rigenerata in CI (stesso bug di Kronos 20/06). Fix: (a) cache xsection versionata + workflow xsection-precompute.yml giornaliero; (b) gate allentato con via di fallback — tsmom + conviction>=2 dai vote accettato anche senza xsection allineato (filtro regime, non collo single-signal). ESITO: RITIRATA. Mai aperto un trade in 3 giorni di paper (gate sempre chiuso anche dopo il fix del 25/06). Non backtestabile (desk LLM). Il track record dimostrativo manca del tutto → nessuna evidenza di edge. Rilevazione manuale di Lorenzo (26/06): 'non sta producendo risultati'. Originally: falsificata se non batteva in paper ne' tsmom puro ne' lux-flow-confluence — non ha mai raggiunto l'evidenza per essere valutata. Conclusione: l'auditor/regime-filter LLM su strategie ibride non produce alpha in questo setup.

## Note evoluzione

v1 — gate tsmom+xsection (ortogonali) + veto event/crowding + conviction vote + layer LLM auditor. Fix 25/06: cache xsection + gate allentato con fallback conviction. Mutazioni: TSMOM_SOLO_MIN_VOTES, larghezza veto, contesto auditor.

## Performance (paper)

- equity: $10,000.00
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 0

## Lezioni

- **thesis_wrong** (basket, —): RITIRATA su rilevazione manuale Lorenzo: strategia ZOMBIE. 0 trade aperti in 3 giorni di paper (gate sempre chiuso anche dopo il fix del 25/06 sulla cache xsection), backtest: {} (non backtestabile, desk LLM). Mai raggiunto l'evidenza per essere valutata. Tesi originale: gate tsmom+xsection + conviction vote + auditor LLM di correlazione. La diagnosi: il forecast/regime-filter LLM su strategie ibride NON produce alpha in questo setup (conferma la lezione 'forecast LLM = niente alpha' documentata gia' in claude-strategy ritirata il 25/06). Inoltre il gate AND a 2 gambe momentum, anche allentato col fallback conviction, resta troppo stringente per produrre trade in regime 2026-H1. Lezione generale: una strategia che NON FA NULLA per giorni, anche se teoricamente 'ortogonale e robusta', e' un costo di opportunita' (slot paper, overhead LLM, rumore nella dashboard) — va ritirata finche' non dimostra di SPARARE. Il track record dimostrativo (agents-v1: 54% win su 13 trade) resta il riferimento per i desk LLM; glm-regime-confluence e' stata rimossa dal workflow cloud (paper-run.yml) e ritirata a status retired. #lifecycle #retire #desk_llm #zombie #no_trades #glm #regime_filter #forecast_no_alpha #rilevazione_manuale

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
