# Handoff — DeFi AI Vault (lux-ai)

> **Per chi entra ora nel progetto e non ha ancora letto il codice.**
> Snapshot al 2026-06-29. Questo file è l'onboarding. La documentazione tecnica canonica resta `README.md`; le note narrative per strategia stanno in `brain/` (vedi §13).

---

## 1. Cos'è, in una frase

Una piattaforma che **fa trading research in modo autonomo e in pubblico**: degli agenti AI (LLM) propongono operazioni con una tesi falsificabile, le eseguono su un conto **paper** (soldi finti, prezzi veri), scrivono il post-mortem quando sbagliano, e fanno *evolvere* le strategie generazione dopo generazione. Il prodotto è la **trasparenza**: ogni tesi, errore e lezione è tracciata e mostrata.

> **Stato: paper trading. Nessun fondo reale è mai stato mosso. Niente nel repo è consulenza finanziaria.**

## 2. Perché esiste — visione e business

Il valore non è "un'AI che indovina il prezzo" (non funziona, lo abbiamo dimostrato e documentato). Il valore è un **sistema che trova edge statistici reali, li valida onestamente, e li gestisce con disciplina di rischio**, mostrando anche le perdite.

Due prodotti, in sequenza:

- **Prodotto 1 — "ricerca in pubblico" (ora).** Una dashboard one-page che mostra journal delle tesi, lezioni dagli errori, e l'albero genealogico delle strategie. Pubblico target: trader retail sofisticati che leggono numeri per mestiere. Riferimento concettuale: Alpha Arena / nof1, ma continuo. Tono: rigoroso, trasparente, zero hype. *Mostrare le perdite è il punto di forza, non un imbarazzo.*
- **Prodotto 2 — vault on-chain (solo dopo track record dimostrato).** Un vault su Hyperliquid (HyperEVM, standard ERC-4626) dove utenti depositano fondi reali gestiti dalla strategia campione. **Questo è M5 e il gate per arrivarci è il TEMPO**, non il codice (vedi §11).

Il design doc completo e le decisioni storiche stanno nel vault Obsidian (`Projects/Active/DeFi AI Vault`).

## 3. Glossario — i concetti che servono per leggere tutto il resto

| Termine | Cosa significa qui |
|---|---|
| **Paper trading** | Conto simulato (parte da 10.000$ fittizi) ma con prezzi di mercato reali. Serve a validare senza rischiare capitale. |
| **Edge** | Un vantaggio statistico misurabile e ripetibile. Per noi è ammesso solo se documentato (IC + t-stat su basket multi-asset) o con tesi accademica solida. Niente "feeling". |
| **Tesi falsificabile** | Ogni trade e ogni strategia deve dichiarare *perché* dovrebbe funzionare E *a quali condizioni è da considerarsi sbagliata* (campo `invalidation` / "Falsificata se:"). Senza tesi+invalidazione, il sistema veta la proposta. |
| **LLM come giudice, non oracolo** | L'AI NON prevede il prezzo. Sintetizza contesto e giudica rischio/correlazione sopra un gate sistematico. Il forecast direzionale LLM = niente alpha (lezione ripetuta, documentata). |
| **Segnale** | Un mattone di calcolo da un registry chiuso (`backtest/signals.py`): l'LLM li *compone*, non inventa codice nuovo. Es: `tsmom`, `xsection_momentum`, `funding_percentile`. |
| **Sharpe** | Rendimento per unità di rischio. Lo misuriamo **per-asset poi mediato sul basket** (mean Sharpe), così una strategia che vince solo su BTC e perde su 8 alt non passa. |
| **DSR (Deflated Sharpe Ratio)** | Sharpe corretto per il fatto che hai provato tante strategie (Bailey–López de Prado). Gate formale: **DSR ≥ 0.95** per promuovere. Protegge dall'overfitting da selezione. |
| **Walk-forward** | Valutazione su finestre temporali successive (e per regime bull/bear/chop), non su tutto il periodo insieme. Più onesto di un backtest piatto. |
| **Champion / challenger** | La strategia campione "in carica" e le sfidanti. Una challenger sostituisce il champion solo se batte i gate statistici di un margine. |
| **Cross-sectional momentum (xsmom)** | Compra gli asset che salgono *più degli altri nel basket*, vende quelli che salgono di meno. È il nostro edge principale. |
| **Dollar-neutral** | Stesso capitale long e short → neutrale al mercato. Cruciale: abbatte il drawdown ~46 punti percentuali rispetto al long-only. |
| **Funding** | Tasso pagato/incassato sui perpetui crypto. Estremi = crowding (tutti dalla stessa parte). |
| **Drawdown (DD / maxDD)** | La perdita massima dal picco. Il rischio di rovina vero è la **coda** del DD, non lo Sharpe medio. |
| **Vol-target overlay** | Scala l'esposizione in modo inverso alla volatilità recente del book (Moreira–Muir). De-riska quando il mercato è turbolento → taglia la coda del DD quasi a costo zero di Sharpe. |

## 4. Come funziona — i due loop

```
INNER LOOP (tattico, ogni 4h)                 OUTER LOOP (evolutivo, giorni)
─────────────────────────────                 ──────────────────────────────
contesto live (prezzi/funding/OI/news)        strategia = artefatto YAML versionato
   → Analyst → dibattito bull/bear                → LLM propone N mutazioni motivate
   → Strategist (tesi falsificabile)              → harness valuta su basket multi-asset
   → HARD LIMITS nel codice (insindacabili)       → walk-forward per fold e regime
   → Risk Manager LLM (approve/reduce/veto)       → selezione → challenger → paper
   → executor paper → stop/target reali           → champion (gate statistico DSR≥0.95)
   → Reviewer post-mortem → LEZIONI
   → recall lezioni nei prompt  ←── il loop si chiude
```

- **Inner loop** = decidere cosa fare adesso. Gira ogni 4h. Pipeline di ruoli LLM (Analyst → Bull/Bear → Strategist → Risk Manager) con limiti di rischio *immutabili scritti in codice* in mezzo, che l'LLM non può scavalcare.
- **Outer loop** = far migliorare le strategie nel tempo. Una strategia è un file YAML versionato; l'LLM propone mutazioni, l'harness le valuta onestamente, le migliori diventano sfidanti, le sfidanti vincenti diventano campioni.

## 5. Stato attuale — cosa gira in produzione OGGI

Tutto gira **engine a portafoglio dollar-neutral**. Il loop "per-simbolo" è stato **svuotato** il 26/06: tutte le strategie single-asset erano rumore (Sharpe 0.12–0.71 contro xsmom 2.11).

| Strategia (file in `strategies/generated/`) | Sharpe (backtest 12m) | maxDD | Ruolo |
|---|---|---|---|
| `xsmom-port-v1` | 2.11 | -19% | **core** — cross-sectional momentum, unico edge forte standalone |
| `highvol-port-v1` | 2.32 | -22% | 2° edge ortogonale (long alt volatili / short blue chip calmi), corr solo +0.28 → diversifica davvero |
| `xsmom-highvol-combo-v1` (blend 50–70/30) | ~2.6–2.75 | **-16%** | best risk-adjusted |
| `xsmom-highvol-voltarget-v1` | ~2.68 | **-11.3%** | combo + vol-target overlay: coda di rovina **azzerata** (P(DD<-25%): 3%→0%) |

Il **vol-target overlay è cablato live** in `paper/portfolio_paper.py` e sta accumulando track record reale — *è il vero gate verso M5*.

I **desk LLM** (`agents-v1`, `claude-strategy-v1`, `glm-regime-confluence-v1`, `geopolitics-v1`) restano attivi solo per il **track record live dimostrativo** (agents-v1: 54% win su 13 trade). Non sono l'edge; sono la vetrina "AI che ragiona".

**Dato operativo:** i file paper (`paper/state.json`, `journal.jsonl`, `decisions.jsonl`, `lessons.jsonl`) sono aggiornati al 28/06 15:05 dal cron cloud — il sistema sta girando regolarmente.

## 6. Mappa del repository — cosa c'è in ogni cartella

| Path | Cosa contiene |
|---|---|
| `README.md` | Documentazione tecnica canonica + risultati dettagliati. La fonte di verità. |
| `CLAUDE.md` | Le 10 regole di progetto insindacabili (rischio, LLM-giudice, gate statistici…). Leggere per prime. |
| `PRODUCT.md` | Brief di prodotto/brand per la dashboard (utenti, tono, design principles). |
| `brain/` | **Note narrative in italiano, una per strategia** + `glossary.md`, `timeline.md`, `lessons.md`. **Il posto migliore per capire senza leggere codice.** |
| `strategies/` + `strategies/generated/` | Le strategie come file YAML versionati. `FORMAT.md` spiega lo schema. |
| `backtest/` | Il motore: `engine.py` (exchange simulato anti-lookahead, fee, funding storico, slippage, liquidazione), `signals.py` (registry segnali chiuso), `strategy.py`, `walkforward.py`, `lifecycle.py` (validazione rischio + stats paper). |
| `scripts/` | ~52 script: i 3 `fetch_*` (dati), `run_strategy.py` (backtest singolo), `evolve.py` (loop evolutivo), `decide.py` (pipeline agenti), `promote.py` (gate champion/challenger), `review.py` (post-mortem→lezioni), `dashboard.py` (genera la dashboard), `llm.py` (layer LLM unificato), `robustness_portfolio.py`, `voltarget_portfolio.py`, `cron_run.sh` (run 4h). |
| `paper/` | **Il "prodotto pubblico"**: journal trade, decisioni con tesi, lezioni, stato conto. File `.jsonl` append-only. |
| `pipeline/` | Dati live (Binance, yfinance, OI, news RSS da 6 fonti). |
| `data/` | Dati storici candele/derivati. **Non nel git**, si rigenerano con i fetch (~5 min). |
| `prompts/roles.yaml` | I prompt degli agenti LLM, centralizzati e versionati (ruolo → system + effort + schema). |
| `db/` + `supabase/` | Schema Postgres/Supabase (trades, decisions, lessons con pgvector, equity_snapshots). |
| `dashboard/` | Output statico della dashboard (HTML zero-dipendenze). |
| `tests/` | Suite test (regression sui bug storici inclusi). |
| `.github/workflows/` | L'automazione cloud (vedi §7). |
| `infra/`, `.kronos/`, `.firecrawl/`, `.agents/` | Tooling di supporto (infra, modello Kronos OHLCV, scraping, config agenti). |

## 7. Dove vive il sistema — architettura cloud-first

Il Mac è **solo dev box**: nessun processo produttivo gira in locale.

- **Esecuzione**: **GitHub Actions**. Il `paper-run.yml` orario fa decide+review+promote+evolve. Trigger orario via **Cloudflare Worker** (clock affidabile: lo scheduler nativo di GitHub salta i repo privati). Workflow separati per i precompute pesanti fuori dall'hot path: `kronos-precompute`, `gdelt-precompute`, `xsection-precompute`, `hl-snapshot`, `coinalyze-1h`, `paper-exits` (gestisce TP/SL).
- **Dashboard**: statica su **Cloudflare Pages** → **`lux-ai.pages.dev`**, deployata dal workflow `deploy-dashboard.yml`.
- **Database**: **Supabase** (Postgres). Sync incrementale idempotente dal journal (`sync_supabase.py`). Recall semantico via pgvector cablato (embedding da popolare — vedi §10).
- **LLM**: un solo modello, **GLM-5.2**, via **OpenRouter** (slug `z-ai/glm-5.2-20260616`). Layer unificato in `scripts/llm.py` con effort differenziato per ruolo, structured output nativo, self-consistency (majority vote N=3) e cache client-side.

## 8. Come farlo girare in locale (per esplorare)

```bash
cd ~/PROGETTI/defi-ai-vault
uv sync                                              # installa dipendenze (usa uv, non pip)
uv run scripts/fetch_universe.py && uv run scripts/fetch_candles.py && uv run scripts/fetch_derivs.py   # rigenera dati (~5 min)
uv run scripts/run_strategy.py strategies/generated/xsmom-port-v1.yaml BTC 6   # un backtest
uv run scripts/dashboard.py && open dashboard/index.html                       # genera e apri la dashboard
uv run pytest                                        # suite test
```

Per vedere il sistema "vivo" senza toccare nulla: apri **`lux-ai.pages.dev`** nel browser.

## 9. Cosa abbiamo imparato — l'onestà del progetto

La forza del progetto è quanto abbiamo **falsificato onestamente**. Sintesi:

- **L'unico edge forte standalone è `xsmom` crypto** (cross-sectional momentum). Cercare un secondo edge è diminishing returns: 8 fattori + cross-asset testati, quasi tutti falsificati.
- **Secondo edge ortogonale trovato**: `highvol` (anomalia di volatilità). Correlazione solo +0.28 con xsmom → diversificazione genuina. La combo dei due ha il miglior drawdown del progetto.
- **Il dollar-neutral è cruciale** (-46pp di drawdown vs long-only). Su asset *correlati*: crypto+commodities mischiati rovinano l'edge (corr ~0).
- **L'LLM come price-predictor non dà alpha** — confermato ripetutamente. Vale come giudice di rischio/correlazione, non come generatore di segnale.
- **Il regime 2026-H1 premia il trend, punisce il mean-reversion**: fade VWAP (7/7 asset), scalp su crowding, stop più stretti dell'invalidazione → tutti falsificati.
- **La certezza statistica non si compra con più backtest sugli stessi dati.** 12 mesi (~50 ribilanci settimanali) NON bastano a inchiodare uno Sharpe (intervalli di confidenza ±2). **Serve tempo, cioè track record forward.** Questo è il motivo per cui M5 è un gate di tempo.

Le strategie in produzione sono **promettenti ma non ancora provate**. Tutte le tesi falsificate sono in `paper/lessons.jsonl` e raccontate in `brain/lessons.md`.

## 10. Cose aperte / debito da sistemare

1. **README disallineato sul backend LLM (priorità alta).** Il README descrive ancora GLM-5.2 via *Z.ai Coding Plan*. La realtà del codice (`scripts/llm.py`, commit `b246ffa`) è **OpenRouter** (`z-ai/glm-5.2-20260616`, auth `OPENROUTER_API_KEY`). → da aggiornare nel README.
2. **`HARD_LIMITS_BYPASS` attivo nel cron cloud** (commit `cbd9d6f`): il sizing dei desk LLM è temporaneamente delegato all'LLM. Da decidere se richiuderlo.
3. **Salute cron**: `paper-exits` ha avuto raffiche di fallimenti (concurrency group condiviso `paper-run`). Tenere d'occhio i run su GitHub Actions.
4. **Embedding pgvector su Supabase**: schema + sync cablati, gli embedding sono da popolare (abilita il recall semantico delle lezioni).
5. **TODO tecnici aperti**: `docs/TODO-sizing-clamp.md`, `docs/worker-xsection-trigger.md`.

## 11. Roadmap e il gate verso i soldi veri

- [x] **M1** — dati, harness, registry segnali, formato strategia, loop evolutivo (3 generazioni)
- [x] **M2** — paper trading live in cron, pipeline agenti end-to-end, reflection loop, CLI autonoma in cloud
- [x] **M3** — champion/challenger con gate statistico formale (DSR ≥ 0.95); journal → Supabase; dashboard su Cloudflare Pages
- [x] **M4** — testnet Hyperliquid (`execute_testnet.py`, dry-run sicuro, **isolato da ogni workflow** per la regola "paper only")
- [ ] **M5 — vault HyperEVM (ERC-4626)** → soldi reali on-chain. **Gate di TEMPO, non di codice.**

**Cosa manca davvero a M5:** niente ingegneria. Serve che le strategie paper, accumulando track record nel tempo (mesi), dimostrino un edge robusto *forward*. `promote.py` è il gate formale che decide quando il track record è "dimostrato". Finché non lo è, non si muove un euro.

## 12. Priorità — prossimi step concreti

1. **Lasciar maturare il track record paper** — è IL gate. Niente nuova caccia all'edge (diminishing returns dimostrato).
2. **Allineare il README** sul provider LLM (debito #1).
3. **Decidere su `HARD_LIMITS_BYPASS`** (debito #2).
4. **Monitorare i cron** su GitHub Actions, in particolare `paper-exits`.
5. **Popolare gli embedding pgvector** per chiudere il recall semantico.

## 13. Da dove iniziare a leggere (consigliato, in ordine)

1. **`PRODUCT.md`** — cos'è il prodotto e per chi (5 min).
2. **`CLAUDE.md`** — le 10 regole insindacabili: capisci subito la filosofia rischio/LLM/gate (10 min).
3. **`brain/glossary.md` + `brain/timeline.md`** — concetti e storia raccontati in italiano, zero codice.
4. **`README.md`** sezione "Risultati finora" — gli edge e le falsificazioni con i numeri.
5. **`brain/xsmom-port-v1.md`** — la nota narrativa dell'edge principale.
6. La dashboard live: **`lux-ai.pages.dev`** — il sistema in funzione.

## 14. Regole dure — cosa NON fare mai

- **Mai muovere fondi reali** senza richiesta esplicita. `execute_testnet.py` resta isolato, fuori da ogni workflow.
- **Mai usare l'LLM come price-predictor.** È giudice di rischio, non oracolo.
- **Mai promuovere su backtest solo o su singolo asset.** Il gate è paper trading + mean-Sharpe su basket.
- **Mai ri-calibrare i parametri su finestre corte.** xsmom overfitta: lb240/reb48 fa Sharpe 3.53 in-sample → -0.79 OOS.
- **Mai aggiungere un segnale al registry** senza backtest pubblico (IC + t-stat) o tesi accademica di riferimento.
