# Dashboard — Miglioramenti UI/UX

Audit del 2026-07-06 su https://lux-ai.pages.dev (desktop, tutte le sezioni).
Target: persone comuni (non-tecniche), spiegare semplice tenendo il tecnico affiancato.
Punti di forza da NON toccare: identità dark, copy onesto ("ammette quando sbaglia",
badge PAPER TRADING), feed decisioni con tesi + falsificazione, lezioni in pubblico.

Ordine di implementazione consigliato: 1 → 3 → 4 → 5 → 2, poi il resto.

## Alto impatto

- [x] **1. Riquadro "Cosa è successo oggi"** — digest di 3 frasi in italiano piano,
  generato dall'LLM a ogni run in `dashboard.py`, mostrato sopra il grafico.
  Es: "Oggi il sistema ha aperto 2 posizioni (oro, petrolio). La migliore della
  settimana è Combo momentum (+4,1%). Ieri ha ammesso un errore su GOLD."
  La pipeline LLM c'è già: è un prompt in più.

- [x] **2. Nav: da 13 voci a 4-5 gruppi** — "Book", "LLM", "Backtest" non dicono
  nulla al target. Raggruppare: **Oggi** (stato+posizioni) · **Strategie**
  (strategie+portafogli+backtest+evoluzione) · **Diario** (decisioni+lezioni+book)
  · **Contesto** (eventi+news+rischio+llm).

- [x] **3. Nomi coerenti ovunque** — in legenda convivono "Agenti LLM" e
  "liqimb-port-v1"/"xsmom-reb48-v1". Un nome amichevole ovunque (grafico, card,
  filtri decisioni), id tecnico solo in tooltip/sottotitolo.

- [x] **4. Grafico aggregato: basta spaghetti** — 11 linee illeggibili. Default:
  solo top 3 + bottom 3 (o media aggregata con banda), le altre spente; click
  sulla legenda per accendere/spegnere. La legenda diventa indice dei conti.

- [x] **5. Numeri negativi con contesto** — "P&L −2454 $, win 29%" spaventa e basta.
  (a) benchmark affiancato: "vs andamento S&P 500: −8,1%";
  (b) riga verdetto in linguaggio piano: "il sistema è sotto del 2,4% dall'avvio:
  normale in questa fase, l'edge si misura su mesi".

## Medio impatto

- [x] **6. Card conti compatte** — 10 conti × ~400px = scroll infinito. Vista
  compatta di default (riga: nome, equity, sparkline 60px, P&L), click per
  espandere. Nascondere celle "0 · 0" (chiusi·vinti) quando non c'è nulla.

- [x] **7. Albero evolutivo visuale** — oggi lista testuale indentata; farne un
  albero orizzontale con nodi colorati per status (colori già definiti).
  Con l'evoluzione giornaliera crescerà molto: collapse per famiglia con
  contatore ("tsmom-aggressive: 6 attive, 12 ritirate").

- [x] **8. Glossario inline** — `dollar-neutral`, `drawdown`, `gross`, `sharpe`
  compaiono nudi nelle card. Tooltip tap/hover (sottolineatura puntinata) con
  spiegazione di una frase — stesso pattern delle intro di sezione.

- [x] **9. Timestamp relativi** — "6 lug · 13:31 UTC" → "2 ore fa" (assoluto in
  tooltip).

## Da verificare / piccoli

- [x] **10. Mobile** — risolto dal punto 2 (4 gruppi entrano in 375px; fade di
  overflow su entrambe le righe). Verificato in preview a 375×812; resta il
  controllo su device fisico.
- [x] **11. Badge feed** — "FEED IN ATTESA" vs "LIVE · 44/79 · HL WS" ambiguo per
  un non-tecnico: tooltip che spiega lo stato.
- [ ] **12. Dominio custom** — al posto di lux-ai.pages.dev: credibilità.

## Note tecniche

- Sorgente: `dashboard/template.html` (2658 righe) + `scripts/dashboard.py` (1033).
- Il deploy avviene nel workflow `paper-run` (step dashboard + wrangler pages).
- Attenzione al pattern già documentato nel workflow: il template va committato
  PRIMA di un run in corso o il deploy del run lo sovrascrive.
