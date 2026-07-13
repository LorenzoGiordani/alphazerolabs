# Prompt per Claude (design) — interfaccia "AlphaZero Labs — ricerca in pubblico"

Progetta una landing/dashboard one-page per una piattaforma di trading research autonoma. Output: **un singolo file HTML statico** (CSS e JS inline, niente framework, niente backend, niente CDN) che io poi popolerò con dati reali iniettati come JSON in un tag `<script id="data" type="application/json">`.

## Cosa è il prodotto

Una pipeline di agenti AI che fa trading research in pubblico: propone trade con tesi esplicite e falsificabili, li esegue su un conto **paper** (balance fittizio 10.000$, prezzi reali di mercato), sbaglia, scrive post-mortem, impara, e fa evolvere le proprie strategie di generazione in generazione. Il prodotto È la trasparenza: ogni tesi, errore e lezione è pubblica. Ispirazione: nof1.ai / Alpha Arena (leaderboard di LLM che tradano), ma continuo e con la storia evolutiva visibile.

Audience: trader retail sofisticati e curiosi di AI. Tono: onesto, tecnico, zero hype — il sito mostra anche le perdite e le tesi falsificate, è il punto di forza.

## Sezioni (in ordine)

1. **Header sticky**: nome prodotto, badge "PAPER TRADING — nessun fondo reale", timestamp ultimo aggiornamento UTC.
2. **Hero/stato**: 2 account affiancati — "Agenti LLM" (pipeline decide i trade) e "TSMOM challenger" (strategia sistematica multi-asset). Per ciascuno: equity, P&L realizzato, n. posizioni aperte, equity curve (SVG/canvas, con assi e tooltip se possibile).
3. **Posizioni aperte**: tabella — asset, lato (long/short con colore), entry, size, stop, target, aperta da. Asset misti: BTC, ETH, oro, petrolio, argento, SP500, stock.
4. **Feed decisioni** (il cuore): card verticali in ordine cronologico inverso. Ogni card: timestamp, asset + direzione, verdetto del Risk Manager (approve/reduce/veto con colore), la **tesi** (3-4 frasi), l'**invalidazione** ("cosa la smentisce"), esito se chiusa (P&L con colore). Deve leggersi come un journal di un desk, non come una tabella.
5. **Lezioni apprese**: timeline o card — verdetto (thesis_wrong / execution_issue / thesis_right), testo della lezione, tag. È il "learning in pubblico": dare risalto agli errori ammessi.
6. **Albero evolutivo strategie**: lineage parent→figli (generazioni di mutazioni), con status (candidate/challenger/champion/retired), Sharpe, e la nota di mutazione. Anche solo una lista indentata ben fatta va bene; un mini-grafo è bonus.
7. **Footer**: disclaimer (ricerca, non consulenza finanziaria; paper trading; performance simulate).

## Forma dei dati (JSON che inietterò)

```json
{
  "updated_utc": "2026-06-12 08:00",
  "accounts": [{
    "id": "agents-v1", "label": "Agenti LLM", "equity": 9948.44,
    "pnl_realized": -50.92, "trades_closed": 1, "wins": 0,
    "equity_curve": [["2026-06-11T21:50", 10000.0], ["2026-06-12T07:52", 9948.44]],
    "positions": [{"symbol": "ZEC", "direction": "long", "entry_px": 433.19,
                   "size_usd": 1428.57, "stop_px": 418.03, "target_px": 463.51,
                   "opened_at": "2026-06-11 20:00"}]
  }],
  "decisions": [{
    "ts": "2026-06-11 21:46", "symbol": "ZEC", "direction": "long",
    "risk_verdict": "reduce", "size_multiplier": 0.5,
    "thesis": "Short crowding estremo: funding -39% APR con prezzo in rimbalzo...",
    "invalidation": "Chiusura 1h sotto 415 o funding che normalizza senza progresso.",
    "outcome": {"closed": true, "reason": "stopped", "pnl_usd": -50.92}
  }],
  "lessons": [{
    "ts": "2026-06-12 07:55", "scope": "ZEC", "verdict": "execution_issue",
    "lesson": "Lo stop deve coincidere con l'invalidazione dichiarata...",
    "tags": ["execution", "stop-placement"]
  }],
  "lineage": [{"id": "funding-squeeze-breakout-v1", "parent": null, "status": "retired", "sharpe": -1.04, "note": "baseline"},
              {"id": "funding-squeeze-breakout-g2", "parent": "funding-squeeze-breakout-v1", "status": "retired", "sharpe": 0.69, "note": "fade del crowding"},
              {"id": "tsmom-v1", "parent": null, "status": "challenger", "sharpe": 1.69, "note": "time-series momentum multi-asset"}]
}
```

Il JS deve leggere questo JSON e renderizzare tutto (così rigenero solo i dati, mai il markup).

## Direzione visiva

- Dark, da terminale finanziario ma caldo — NON il solito gradiente viola AI, NON Inter/Roboto. Proponi una palette e una coppia tipografica con carattere (es. una serif/slab per i titoli + mono per i numeri). I numeri sono protagonisti: tabular figures.
- Verde/rosso per P&L e long/short, ma raffinati (non #00ff00).
- Le card delle decisioni devono sembrare pagine di un journal: leggibili, con gerarchia tipografica vera.
- Mobile-first responsive. Massimo rispetto per la densità informativa: è un prodotto per gente che legge numeri.
- Micro-dettagli benvenuti: hover sulle righe, transizioni sobrie, sparkline animata al load. Niente che richieda librerie.

## Vincoli tecnici

- Un solo file HTML, zero dipendenze esterne (no Google Fonts via CDN: usa system stack o font-face con fallback dichiarati).
- Charts in SVG generato da JS vanilla.
- Deve funzionare aperto da file:// e pubblicato su Cloudflare Pages.
- Tutte le stringhe UI in italiano.
