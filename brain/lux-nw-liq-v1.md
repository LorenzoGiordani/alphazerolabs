# lux-nw-liq-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **parent**: [[lux-nw-continuation-v1]]
- **created**: 2026-06-26

## Tesi

CONFLUENCE PREZZO-STRUUTTURA + FLUSSO FORZATO. Due edge INDIPENDENTI e validati:
  - nadaraya_watson (continuation, edge_only) = il prezzo ha ROTTO la banda
    kernel-MAD → espansione strutturale volatility-adaptive (IC +0.105, t+5).
  - liq_imbalance (edge_only) = liquidazioni forzate a estremo (squeeze/capitola-
    zione Coinalyze multi-exchange) → carburante direzionale. L'UNICO segnale di
    flusso sopravvissuto a tutte le falsificazioni del progetto (funding, OI, news,
    kronos direzionale: tutti morti; liq resta).
Perché dovrebbe battere il champion (tsmom+liq): sostituisce il tsmom (segno del ritorno grezzo, una pendenza) con un breakout kernel-MAD strutturale. Il tsmom entra a LIVELLI qualsiasi (basta che 7g+30g siano verdi), anche a fine trend; il NW entra solo su ROTTURE di banda = timing migliore. Le due gambe qui sono ortogonali per costruzione (prezzo-struttura vs flusso forzato), a differenza di NW+tsmom (entrambi momentum, correlati → AND falsificato, vedi lux-nw-tsmom). Falsificata se: in walk-forward basket 9-asset non batte lux-flow-confluence (champion) su mean Sharpe/DSR. Se il NW non aggiunge valore sul tsmom a parità di gamba liq, il champion resta e NW resta come standalone (lux-nw-continuation).

## Note evoluzione

v1 seed: NW-continuation + liq_imbalance (ortogonali: struttura vs flusso). Mutazioni: soglia mult NW, extreme_pct liq, time_stop, aggiunta tsmom come terza gamba (test di robustezza, non di principio).

## Performance (paper)

- equity: —
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 0

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
