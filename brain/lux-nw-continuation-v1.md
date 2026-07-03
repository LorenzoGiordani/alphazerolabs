# lux-nw-continuation-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **created**: 2026-06-26

## Tesi

BREAKOUT KERNEL-ENVELOPE (Nadaraya-Watson). Quando il prezzo rompe la banda superiore/inferiore di un envelope kernel-regression (Gaussian one-sided, kernel- MAD), l'espansione è strutturale e CONTINUA nella direzione del break. Tesi DaviddTech (Nadaraya-Watson Envelope) adattata al regime 2026-H1: qui il trend domina e il mean-reversion è falsificato (VWAP fade 7/7 persi, lezione 12/06), quindi la lettura è CONTINUATION (follow), non fade. Edge VALIDATO (research_nw.py, basket 9-asset 12m, 25/06): il segnale NW come continuation ha IC +0.105 (t +5.0) a orizzonte 48h (params lb=72, mult=2.0) e +0.074 (t +3.4) a 168h. Il fade ha IC NEGATIVO → falsificato nel regime corrente. Perché dovrebbe battere range_breakout: baseline kernel-smoothed (non equal-weighted come un rolling max/min) + bande MAD volatility-adaptive → isola l'espansione reale dal rumore, riduce i falsi break del range_breakout classico. Ortogonale al tsmom (che usa il SEGNO del ritorno grezzo): NW cattura il breakout strutturale, non la pendenza. Falsificata se: in walk-forward basket 9-asset non raggiunge mean Sharpe ≥0.3 e DSR ≥0.5, oppure non batte buy-and-hold risk-adjusted sui 12m.

## Note evoluzione

v1 seed: segnale NW (continuation) da solo — isola il nuovo edge senza confonderlo col momentum. Mutazioni: lookback/bandwidth/mult (sweep dell'IC study), aggiunta di tsmom come gamba di confluence (→ lux-nw-tsmom), time_stop più corto (match 48h).

## Performance (paper)

- equity: —
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 0

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
