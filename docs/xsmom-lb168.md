# xsmom LB168 — specifica di sviluppo

Strategia **core** del progetto AlphaZero Labs: cross-sectional momentum dollar-neutral a portafoglio, lookback 168h. Questo documento è la specifica per implementarla/validarla. È l'edge più testato del progetto (sopravvissuto a settimane di iterazione e al refactor da per-simbolo a portafoglio). **Leggere i caveat (§6) prima di fidarsi dei numeri.**

Artifact di riferimento già esistente: `strategies/generated/xsmom-port-v1.yaml` (`status: challenger`, `engine: portfolio`).

---

## 1. Tesi (falsificabile)

Cross-sectional momentum: nel basket crypto il ritorno relativo degli ultimi 7 giorni (168h) ha potere predittivo sul ritorno relativo della settimana successiva. Costruito come **book dollar-neutral** (long il terzile forte, short il terzile debole) netta il beta comune del basket e scommette solo sullo **spread relativo** mantenuto nel tempo.

**Falsificata se**: in walk-forward multi-regime il book dollar-neutral non batte l'equal-weight B&H risk-adjusted, o se l'edge sparisce coi costi reali di ribilanciamento.

## 2. Specifica matematica esatta

**Universo**: 9 perp Hyperliquid liquidi: `BTC, ETH, SOL, XRP, SUI, NEAR, WLD, ZEC, CRV`. In produzione: `universe.selection: all_perps` risolve live i perp con volume ≥1M$/24h.

**Prezzo**: close orario (1h), panel `close[ts, symbol]`. Griglia sull'ora BTC (24/7), `ffill` per asset session-based.

**Segnale** (per timestamp t, anti-lookahead: usa solo dati ≤ t):
```
trailing_ret_i(t) = close_i(t) / close_i(t - 168h) - 1
```

**Pesi** (`xs_momentum_weights`, vedi `backtest/portfolio.py`):
- `long_q = 0.66`, `short_q = 0.33` (terzile)
- Long gli asset con `trailing_ret ≥ quantile(0.66)`, short quelli `≤ quantile(0.33)`.
- Equal-weight per gamba: `+0.5/n_long` sui long, `−0.5/n_short` sui short.
- `gross = 1.0` (somma dei valori assoluti = 1.0).
- `dollar_neutral = true`: Σ pesi = 0 (netta il beta di mercato).
- Se `< 3` asset validi → pesi tutti zero (skip rebalance).

**Rebalance**: ogni `rebalance_h = 168h`.

**P&L** (anti-lookahead: pesi decisi a t, applicati dal bar t+1):
```
port_ret(t) = Σ_i [ W_i(t-1) · ret_i(t) ]  -  turnover(t) · cost
ret_i(t)    = close_i(t)/close_i(t-1) - 1
turnover(t) = Σ_i | W_i(t) - W_i(t-1) |     # solo ai bar di rebalance
cost        = HL_TAKER_FEE + DEFAULT_SLIPPAGE = 0.00045 + 0.0002 = 0.00065
equity      = (1 + port_ret).cumprod()
```

## 3. Metriche da produrre (gate anti-overfitting)

Per ogni periodo/regime: **total_return, Sharpe (annualizzato √(24·365)), max_drawdown, DSR** (Deflated Sharpe, `backtest/stats.py:deflated_sharpe`). Confronto obbligatorio vs **equal-weight B&H** (`backtest/portfolio.py:equal_weight_bh`).

Soglia di promozione "zoo": **Sharpe > 1 AND DSR ≥ 0.5**. Soglia di promozione a live: **DSR ≥ 0.95** + track record paper forward.

## 4. Numeri di riferimento (con riserve — vedi §6)

Backtest 12m, basket 9, con costi, `xs_momentum_weights` (metodo canonico):

| Finestra | Ret | Sharpe | maxDD | DSR |
|---|---|---|---|---|
| 12m corrente (2025-07 → 2026-07) | +201% | 3.73 | −11.8% | 1.00 |
| primi 6m (2025-07 → 2026-01) | +129% | 5.40 | −9.5% | — |
| YAML canonico (calcolato ~22/06) | +80% | 2.11 | −19.4% | 0.91 |

equal-weight B&H stesso periodo: −17% / Sharpe 0.08 / maxDD −59%.

**L'edge batte il benchmark di molto.** Ma i numeri assoluti oscillano (2.1 ↔ 5.4) col periodo — vedi §6.

## 5. Mappa del codebase (RIUSA, non riscrivere)

| Componente | File | Note |
|---|---|---|
| Harness portfolio | `backtest/portfolio.py` | `PortfolioBacktest`, `xs_momentum_weights`, `equal_weight_bh`. **È questo il backtest.** |
| Deflated Sharpe | `backtest/stats.py` | `deflated_sharpe(rets, n_trials, trial_srs)`. |
| Costi engine | `backtest/engine.py` | `HL_TAKER_FEE`, `DEFAULT_SLIPPAGE`, `DEFAULT_FUNDING_HOURLY`. |
| Runner paper | `scripts/portfolio_paper.py` | supporta già `factor: xsmom` → ribilancia live. |
| Factor zoo (confronto) | `scripts/backtest_factor_zoo.py` | `grid_panel`, `terzile_weights`, `run_factor`, `stats`. |
| Robustness | `scripts/robustness_portfolio.py` | griglia param + block bootstrap CI. |
| Artifact | `strategies/generated/xsmom-port-v1.yaml` | YAML canonico da aggiornare coi risultati. |
| Dati prezzo | `data/candles/<SYM>.parquet` (col `close`, `ts`). |
| Dati funding | `data/funding/<SYM>.parquet` (col `rate`, 3x/day, per-intervallo 8h). |

`xs_momentum_weights` + `PortfolioBacktest.run` fanno già quasi tutto. Non servono nuove classi.

## 6. ⚠️ Caveat critici (NON ometterli nel report finale)

Questi sono i motivi per cui i numeri del §4 **non sono previsioni**:

1. **Funding non modellato (BIAS verso l'alto, ~3-4%/anno).** xsmom è dollar-neutral ma il funding **non si azzera** — è asimmetrico (long i forti con funding+, short i deboli con funding−). Il P&L qui sopra **non lo sottrae**. Da aggiungere: cashflow `Σ_i (−W_i · r_i / 8)` per-intervallo-8h (vedi `backtest_funding_carry.py` per il pattern corretto — **dividere per 8**: il rate è per-intervallo, non orario. Un bug del genere ha gonfiato il carry di 8×).
2. **Rumorosità statistica.** ~50 ribilanci/anno. Lo Sharpe varia da 2.1 a 5.4 a seconda della finestra di 12m. Il DSR 1.00 non significa "skill certa" — significa "su pochi trial contati, non falsificata". Serve **più anni** per inchiodare la stima.
3. **Selection bias / multiple testing.** L'edge è il massimo di tanti trial (per-simbolo + factor zoo + sweep orizzonti/quantili). Il `n_trials` nel DSR va contato in modo conservativo (k sottostimato → DSR troppo ottimista).
4. **Survivorship bias nel basket.** I 9 ticker sono liquidi *oggi*; gli asset morti/delisted nel periodo non ci sono (tipicamente i peggiori, dove lo short sarebbe stato profittevole).
5. **Regime / degradazione.** Sharpe 5.40 nei primi 6m → 3.73 sui 12m: la seconda metà tira giù, il momentum sta rallentando. In regime di chopping/whipsaw il momentum è storicamente disastroso (piccole perdite a ogni inversione). Il maxDD "−11.8%" riflette un periodo fortunato, non la coda reale.
6. **Slippage su gambe illiquide.** Lo slippage size-aware square-root c'è ma il book ribilancia capitale pieno anche su ZEC/CRV; l'impatto reale nel live è probabilmente maggiore.

## 7. Task di sviluppo / validazione (cosa manca davvero)

- [ ] **Modellare il funding** nel P&L (caveat §6.1) — riusare il pattern di `backtest_funding_carry.py:run_carry` (cashflow `−W·r/8`).
- [ ] **Walk-forward multi-regime**: split su ≥3 fold fuori-sample mai toccati nel tuning; riportare Sharpe per fold, non solo pooled.
- [ ] **Parametri congelati**: tarare lookback/quantili solo su BTC → congelare → valutare sugli altri 8 asset mai visti nel tuning (test anti-overfit più duro).
- [ ] **Griglia robustezza**: lookback {24,48,96,168,336}h, gross {0.5,1.0,1.5}, long_q {0.6,0.66,0.75}; richiedere struttura monotona + 100% celle > baseline.
- [ ] **Per-simbolo**: % asset con contributo positivo (un edge reale è diffuso, non concentrato).
- [ ] **Block bootstrap CI** sullo Sharpe (`robustness_portfolio.py`): CI95-inferiore > 1.0 è la vera soglia di credibilità (oggi non passa a 12m — serve tempo).
- [ ] **Track record paper forward** (gate G4): mesi di `portfolio_paper.py` su dati live prima di qualsiasi capitale reale.

## 8. Self-check (verificare dopo lo sviluppo)

```python
# minimo: il backtest deve riprodurre questi numeri sul 12m corrente
# xs_momentum_weights + costi, rebalance 168h, basket 9:
#   Sharpe ≈ 3.7 (±0.3), ret ≈ +200%, maxDD ≈ −12%
# Se dà ~2.1 o ~5.4 → controllare la finestra temporale (caveat §6.2)
# equal-weight B&H stesso periodo: Sharpe ≈ 0.08, ret ≈ −17%
```

---

## Contesto decisionale

xsmom LB168 è l'edge **core** del portafoglio. Le due strategie di Fase 2 testate a fianco sono entrambe bocciate: **residual-mom** (Blitz, Sharpe 3.63 < raw 3.73 → falsificata) e **funding-carry** (Sharpe 1.08 / DSR 0.26 dopo fix di un bug che ne gonfiava la cassflow funding 8× → debole). La terza candidata Fase 2 (tsmom regime-gated HMM) resta da testare. Quindi xsmom + highvol + combo restano il portafoglio attivo; questo documento è per validare/irrobustire xsmom prima di considerarla pronta per capitale reale.
