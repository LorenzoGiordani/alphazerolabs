# claude-strategy-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **created**: 2026-06-22
- **family**: claude-strategy

## Tesi

Strategia ibrida progettata da zero. Tesi: separare CHI trova dal CHI giudica. (1) Un gate SISTEMATICO trova i setup ad alta convinzione = confluenza di flusso forzato (trend tsmom + sbilancio liquidazioni reali liq_imbalance concordi), l'unico edge ortogonale sopravvissuto alle falsificazioni del progetto. (2) Un LAYER LLM (Claude) fa da Portfolio Manager avverso SOLO su quei candidati: giudica regime, funding, news e soprattutto il rischio di correlazione col book — dove l'LLM aggiunge valore — e NON prevede il prezzo, dove l'LLM non ha edge (lezione dura del progetto: forecast LLM = niente alpha). Costo LLM minimo: una chiamata per run e solo a gate aperto. Falsificata se: non batte in paper né tsmom-liq (stesso gate, senza il layer LLM) né il desk agents-v1 — cioè se il giudizio di Claude non aggiunge valore sopra il puro sistematico.

## Note evoluzione

v1 — gate confluenza tsmom+liq_imbalance + layer LLM (Claude PM avverso). Mutazioni possibili: larghezza del gate, contesto passato al PM, regole di sizing per convinzione.

## Performance (paper)

- equity: $10,000.00
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 0

### Trade chiusi

| symbol | reason | exit | PnL |
|---|---|---|---|
| ZEC | reset_backlog |  | $0.00 |
| SUI | reset_backlog |  | $0.00 |
| SOL | reset_backlog |  | $0.00 |

## Lezioni

- **execution_issue** (ZEC, $0.00): Una posizione aperta senza entry price, size o tesi registrata non può essere valutata né gestita: ogni trade deve loggare al momento dell'apertura simbolo, direzione, size, entry, stop, target e tesi falsificabile — altrimenti il close è amministrativo, non operativo. #logging #trade-hygiene #missing-entry-data #process
- **execution_issue** (SUI, $0.00): Un trade chiuso per reset_backlog con PnL zero e open={} indica che la posizione non è mai stata aperta correttamente: il segnale è stato generato ma l'ordine non è mai transitato da intento a esecuzione. Verificare sempre che open{} sia popolato prima di tracciare il trade come attivo; un trade senza entry è noise nel journal, non esperienza. #execution #journal_integrity #order_lifecycle #paper_trading
- **execution_issue** (SOL, $0.00): Un trade che si apre e chiude con PnL=0 e reason='reset_backlog' non è mai stato attivo: position sizing o entry logic hanno fallito prima dell'esecuzione. Verificare sempre che open{} contenga entry_price e size prima di registrare un trade come aperto. #execution #position-sizing #entry-validation #null-trade
- **thesis_wrong** (basket, —): claude-strategy ritirata manualmente 25/06: il layer LLM (Claude PM) sopra il gate tsmom+liq non ha prodotto valore - 3 trade tutti flat, 0 PnL. La tesi "separare CHI trova da CHI giudica" resta valida in linea di principio ma qui l'auditor non ha filtrato meglio del puro sistematico. Il pattern "gate sistematico + LLM auditor" resta in glm-regime-confluence-v1 (che usa un gate ortogonale diverso). #lifecycle #retire #manual #llm-desk #claude-strategy

## Eventi lifecycle

- **retire** (2026-06-25): manuale: 3 trade paper tutti flat (PnL 0), layer LLM non ha aggiunto valore sopra il gate sistematico puro (stesso gate di tsmom-liq, gia ritirata a sua volta)

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
