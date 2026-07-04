# Go-to-market — Prodotto 1: ricerca in pubblico

Lancio pubblico di `lux-ai.pages.dev` come prodotto "research in public": gratis, audience-first.
Obiettivo: andare live **il prima possibile** con il **massimo di sicurezza** (tecnica + reputazionale + legale), a fasi, con gate go/no-go.

> Questo NON è il vault con fondi reali (M5). Quello resta gated dal track record paper nel tempo (vedi Gate G4).
> Principio #1 invariato: paper trading, balance fittizio, niente è consulenza finanziaria.

## Stato di partenza (già pronto)

- Dashboard multipagina costruita (`dashboard/`), titolo, sezioni, design PRODUCT.md.
- Disclaimer + "non è consulenza finanziaria" + label "paper" presenti su tutte le pagine.
- Deploy su Cloudflare Pages automatico (`deploy-dashboard.yml`, push su `dashboard/**`).
- Pipeline dati/decisioni/paper in cron cloud.

Conclusione: il gate al lancio **non è costruire feature**, è **affidabilità + onestà dei claim + processo**.

---

## Le 5 fasi (ogni gate è go/no-go, criteri misurabili)

### Fase 0 — Pre-flight: affidabilità tecnica
Rischio coperto: **tecnico** (dati stale o pipeline rotta visibili in pubblico).
- [ ] Banner "ultimo aggiornamento" sul sito; se i dati sono più vecchi di 8h → avviso visibile, non numeri silenziosamente stale.
- [ ] Smoke test end-to-end: fetch → decide → paper → `dashboard.py` rigenera senza errori.
- [ ] Verifica storico fallimenti workflow (`paper-run`, `paper-exits`); cause note risolte.
- [ ] Rollback provato: `git revert` del deploy → sito torna a stato precedente in <5 min.
- **Gate G0**: 7 giorni di cron senza fallimenti non gestiti **e** zero dati stale >8h sul sito.

### Fase 1 — Honesty & legal audit
Rischio coperto: **reputazionale + legale** (claim fuorvianti, sembrare consulenza/promessa di rendimento).
- [ ] Ogni numero pubblico (Sharpe, ret, DD) etichettato: `paper` / `backtest` / fee incluse / date / periodo.
- [ ] Nessun claim di rendimento futuro o linguaggio "magic". Tono PRODUCT.md: rigoroso, trasparente, caldo.
- [ ] Disclaimer visibile su **ogni** pagina (verificato presente — ricontrollare dopo ogni modifica template).
- [ ] Pagina "Metodo / Onestà": paper trading, anti-lookahead, falsificazione, "mostriamo le perdite".
- [ ] Le perdite e le tesi falsificate hanno la stessa dignità visiva delle vittorie (design principle #1).
- **Gate G1**: checklist claim 100% etichettati · pagina metodo pubblicata · self-review legale con checklist passata.

### Fase 2 — Soft launch (limitato)
Rischio coperto: **validazione** prima dell'esposizione pubblica.
- [ ] Deploy con `noindex` (o URL non promosso); condividi a 5–10 trader fidati (target PRODUCT.md).
- [ ] Analytics privacy-friendly (Cloudflare Web Analytics o Plausible) + monitor uptime + alert su deploy fail.
- [ ] Raccogli feedback: comprensibile? claim credibili/onesti? mobile ok?
- **Gate G2**: ≥5 feedback · 0 issue critici (claim fuorviante, dato sbagliato, illeggibilità mobile) · uptime 100% nella finestra.

### Fase 3 — Public launch
Rischio coperto: **esposizione controllata**.
- [ ] Rimuovi `noindex`; abilita SEO + OpenGraph/Twitter card; dominio definitivo se voluto.
- [ ] Runbook incidenti pronto: cosa fare se la pipeline rompe o un dato è sbagliato live (es. mettere banner "manutenzione", pausa deploy).
- [ ] Annuncio: 1 post che racconta "research in public", linka il metodo, dichiara paper. Zero hype, zero promesse.
- **Gate G3**: post pubblicato · monitoring attivo · runbook scritto e a portata di mano.

### Fase 4 — Sustain & gate verso il vault (M5)
Rischio coperto: **lungo termine + il vero gate ai fondi reali**.
- [ ] Cadenza mantenuta; pubblica lezioni e falsificazioni (è il prodotto).
- [ ] Definisci i criteri **quantitativi** per sbloccare M5, da soddisfare per N mesi consecutivi:
  - track record paper forward OOS (non backtest)
  - Sharpe live dentro l'intervallo di confidenza atteso
  - max drawdown entro la soglia dichiarata
  - deflated Sharpe ≥ 0.95 mantenuto
  - zero incidenti di integrità dati
- **Gate G4 → M5**: criteri sopra soddisfatti per N mesi → solo allora si valuta il vault.

---

## Sequenza dei gate

```
G0 affidabilità → G1 onestà/legale → G2 soft launch → G3 public → G4 (mesi) → M5 vault
```

Ogni gate è bloccante: non si passa al successivo finché i criteri non sono verdi. "Il prima possibile" = comprimere F0–F1 (giorni), non saltare i gate.
