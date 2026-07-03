# lux-regime-3leg-v1

[[README|← Brain index]]

## Anagrafica

- **status**: retired
- **parent**: [[lux-flow-confluence-v1]]
- **created**: 2026-06-26

## Tesi

GATE DI REGIME sul champion (tsmom + liq_imbalance). Il champion lux-flow-confluence (mean Sharpe 1.26, DSR 0.81, 9/9 positivo in backtest) è il live edge più forte, MA la debolezza documentata di ogni strategia momentum è il WHIPSAW nel chop: entra a ogni finta rottura, si fa scippare dallo stop, poi il trend vero parte senza posizione. Cura (DaviddTech: 'regime filter' sempre attivo): aggiungere una terza gamba NON direzionale che GATE solo i periodi trending. hmm_regime = regime 'trending' da un Hidden Markov Model (metodo Renaissance/ Simons: stati nascosti dai ritorni). AND gate: entra SOLO se HMM dice 'trend'. → uccide le entrate in chop senza toccare la direzione (che resta il voto tsmom+liq). Tesi ortogonale alle 2 gambe esistenti: HMM misura la STRUTTURA del mercato (trend vs range), non il livello né la pendenza. Tre fonti indipendenti. Falsificata se: il gate di regime NON migliora il drawdown worst-case e/o il win-rate del champion in walk-forward senza distruggere il numero di trade (under-trading). Un gate che azzerza le entrate è inutile quanto uno assente.

## Note evoluzione

v1 seed: champion + gate hmm_regime (regime filter DaviddTech). Mutazioni: soglia liq extreme_pct, lookback liq, RR 1.8-2.5. NOTA: SOL manca della cache HMM (precompute_hmm da rigenerare) → su SOL degrada a neutro (hmm=0 → entry spenta). Documentato, non un bug.

## Performance (paper)

- equity: —
- trade chiusi: 0 · win rate: 0%
- PnL totale: $0.00
- posizioni aperte ora: 0

## Lezioni

- **thesis_wrong** (basket, —): Un gate di regime NON direzionale (hmm_regime) applicato come terza gamba AND soffoca l'edge del champion: 301 trade vs 1254 (under-trading estremo), 1/9 simboli positivi, 4/54 fold. Il regime-filter di DaviddTech e' valido in principio ma sbagliato come implementazione: deve essere un VETO che sospende nei periodi chop confermati, non un AND che richiede regime trending per entrare. Inoltre la cache hmm manca su alcuni asset (SOL) → degrada a neutro e blocca del tutto l'entry. Lesson: i filtri di regime si applicano come veto/vol-gate, mai come AND stretto. #regime_filter #hmm #veto #under_trading #falsification #backtest

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
