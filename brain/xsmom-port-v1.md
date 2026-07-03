# xsmom-port-v1

[[README|← Brain index]]

## Anagrafica

- **status**: challenger
- **parent**: [[xsmom-v1]]
- **created**: 2026-06-22
- **family**: xsmom-port

## Tesi

Cross-sectional momentum a PORTAFOGLIO: long il top-terzile del basket per forza relativa (ultime 168h), short il bottom-terzile, dollar-neutral, ribilanciato ogni 168h. Lo stesso edge che da -14.5% nell'engine per-simbolo stop-based (l'IC e troppo sottile per trade discreti) rende +29.4% Sharpe 1.97 maxDD -12% a portafoglio (backtest_portfolio.py, basket 9 crypto 6m): l'edge sta nello SPREAD mantenuto, non nel singolo trade, e il dollar-neutral netta il beta comune (corr basket 0.63) abbattendo il drawdown. Turnover basso (25 ribilanci/6m). Falsificata se: in paper il book dollar-neutral non batte l'equal-weight B&H risk-adjusted, o se l'edge sparisce coi costi reali di ribilanciamento.

## Note evoluzione

v1 — primo engine:portfolio. Cross-sectional momentum dollar-neutral settimanale, gross 1.0. Backtest: +29.4%/Sharpe 1.97/maxDD -12% vs B&H -19.9%/-0.36. Mutazioni: lookback, rebalance_h, quantili, gross, vol-weight.

## Performance (paper)

- equity: $9,813.24
- trade chiusi: 146 · win rate: 42%
- PnL totale: $-186.76
- posizioni aperte ora: 6

### Posizioni aperte

| symbol | dir | entry | stop | target | size |
|---|---|---|---|---|---|
| BTC |  |  |  |  | — |
| SOL |  |  |  |  | — |
| SUI |  |  |  |  | — |
| NEAR |  |  |  |  | — |
| WLD |  |  |  |  | — |
| ZEC |  |  |  |  | — |

## Lezioni

- **thesis_wrong** (basket, —): xsmom-port ritirata manualmente 25/06: l'edge cross-sectional momentum e reale (IC positivo significativo) e in backtest il book dollar-neutral faceva +29% vs -20% benchmark, ma in paper trading non ha prodotto trade chiusi (ribilanciamenti continui, niente chiusure per-simbolo). L'engine portfolio e concettualmente giusto ma richiede piu tuning/osservazione. Registro: riprendere l'engine a portafoglio quando il focus torna sul cross-sectional, con book live piu lungo. #lifecycle #retire #manual #portfolio #cross-sectional
- **thesis_right** (basket, —): RIPRESA in produzione 26/06. L'engine portfolio cross-sectional momentum dollar-neutral conferma l'edge a 12m: +79.8% (Sharpe 2.11, maxDD -19%, DSR 0.91) vs benchmark equal-weight -8.8% (maxDD -59%). L'edge (IC +0.089 t+21, il piu' forte misurato) NON era sfruttato perche' non catturabile nel motore per-simbolo (falsificato su 3 varianti: richiede concordanza direzionale long-leader/short-laggardo). E' il vero valore dell'engine portfolio: lo spread mantenuto batte il singolo trade stoppato. Ritirata il 25/06 era per strumentazione paper sbagliata (non registrava open/close, ma logga rebalance/heartbeat con equity) → paper_stats ora deriva le metriche dall'equity curve. Il dollar-neutral e' cruciale: la versione long-only degrada a maxDD -65% (vs -19%), il netting del beta comune e' il vero valore, non il timing. #lifecycle #resume #portfolio #cross_sectional #dollar_neutral #backtest
- **thesis_wrong** (basket, —): Ritirata da challenger: 45 trade paper, basket_meanR -0.00049 (perdente su media per-asset). Il paper trading ha falsificato l'edge. #lifecycle #retire #paper
- **bug_fixed** (basket, —): BUG nel gate promote: ritirava i engine:portfolio su RUMORE. Per i portfolio, _portfolio_stats pone n_closed = # di letture rebalance/heartbeat (cron ogni 4h, autocorrelate), NON trade indipendenti, e basket_mean_r = ritorno per-rebalance. Il gate (n_closed >= min_trades AND mean_r < 0) ritirava quindi un portfolio dopo pochi giorni su un mean_r near-zero. SINTOMO: xsmom-port-v1 ritirata alle 15:21 UTC su 50 letture (~7 giorni), mean_r -0.0005 (-0.05%/rebalance), DD solo -1.94% (entro ogni soglia), equity 9806 (-1.9%). Statisticamente assurdo: 50 letture 4h autocorrelate con -0.05%/rebalance e' puro rumore — lo stesso giudizio prematuro che il README condanna ('12m insufficienti per inchiodare uno Sharpe'). Stessa classe di bug della falsa ritirazione del 25/06 (strumentazione), ma ora nel GATE non nella strumentazione. FIX: per engine:portfolio il gate mean_r/n_closed e' SOSPESO (vale solo il breach di drawdown, l'hard risk limit). Motivazione filosofica coerente col progetto: l'edge di un portfolio e' uno Sharpe lento su MESI, non si falsifica da poche letture; il gate M5 e' TEMPO non codice. xsmom-port-v1 RIRESUMATA a challenger. Regression test aggiunto (test_promote_does_not_retire_portfolio_on_noise). Lezione generale: le metriche derivate (n_closed come proxy) perdono il significato originale quando cambiano engine — un gate che usa n_closed assume 'trade discreti indipendenti', falso per i portfolio. #bugfix #promote #portfolio #false_retirement #selection_bias #noise #gate #lifecycle #regression_test

## Eventi lifecycle

- **retire** (2026-06-25): manuale: engine portfolio, 0 trade chiusi in paper. Edge cross-sectional (IC +0.028, t+4.2) reale ma non catturato dal book in fase di tuning
- **retire** (2026-06-26): basket_mean_r_negative

[[lessons|Tutte le lezioni]] · [[timeline|Timeline]]
