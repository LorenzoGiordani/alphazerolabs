# Glossario segnali

[[README|← Brain index]]

_Definizioni stabili in `scripts/brain_gen.py` (GLOSSARY). Colonna 'in uso' = strategie YAML che montano il segnale._

| segnale | definizione | in uso |
|---|---|---|
| `cot_percentile` | Percentile del posizionamento COT (Commitment of Traders) su future commodity. Estremi = crowding istituzionale. | [[commodities-cot-trend-v1]] |
| `funding_percentile` | Percentile del funding rate su lookback (es. 168h). Estremo = crowding di un lato del book; carburante per squeeze. | [[funding-squeeze-breakout-g2]] [[funding-squeeze-breakout-g2-g1]] [[funding-squeeze-breakout-g2-g1-g1]] [[funding-squeeze-breakout-g2-g1-g2]] [[funding-squeeze-breakout-g2-g1-g3]] [[funding-squeeze-breakout-g2-g2]] [[funding-squeeze-breakout-g2-g3]] [[funding-squeeze-breakout-g3]] [[funding-squeeze-breakout-v1]] [[tmp-g2]] [[tmp-g3]] |
| `hmm_regime` | **TODO: definire** (segnale nuovo, non in glossario) | [[lux-regime-3leg-v1]] |
| `kronos_forecast` | Forecast del foundation model Kronos su serie OHLCV. Segnale predittivo, non reattivo. | [[lux-0.1-beta]] [[lux-confluence-rr2-v1]] |
| `liq_imbalance` | Sbilanciamento delle liquidazioni (long vs short). Spike = potenziale cascata/squeeze. | [[liq-cascade-reversal-v1]] [[lux-0.1-beta]] [[lux-confluence-rr2-v1]] [[lux-flow-confluence-v1]] [[lux-nw-liq-v1]] [[lux-regime-3leg-v1]] [[lux-triple-3orthogonal-v1]] [[tsmom-liq-v1]] |
| `nadaraya_watson` | **TODO: definire** (segnale nuovo, non in glossario) | [[lux-nw-continuation-v1]] [[lux-nw-liq-v1]] [[lux-nw-tsmom-v1]] |
| `news_event` | Trigger event-driven da feed GDELT. Catalizzatore macro/narrativa, non tecnico. | [[geopolitics-v1]] [[lux-0.1-beta]] |
| `oi_trend` | Trend dell'open interest. OI fermo su prezzo che sale = short non capitolati (carburante squeeze). | [[lux-0.1-beta]] |
| `range_breakout` | Rottura di un range multi-day con conferma di volume. Direzione = quella del breakout. | [[funding-squeeze-breakout-g1]] [[funding-squeeze-breakout-g3]] [[funding-squeeze-breakout-g4]] [[funding-squeeze-breakout-v1]] [[tmp-g1]] [[tmp-g3]] [[tmp-g4]] [[vol-expansion-breakout-v1]] |
| `smart_money_ratio` | Rapporto posizionamento large vs retail. Proxy di flusso informato. | [[lux-0.1-beta]] |
| `taker_flow` | Sbilanciamento dei taker aggressivi (buy vs sell). Proxy di pressione direzionale intraday. | [[crypto-trend-flow-v1]] [[funding-squeeze-breakout-g2]] [[funding-squeeze-breakout-g2-g1]] [[funding-squeeze-breakout-g2-g1-g1]] [[funding-squeeze-breakout-g2-g1-g2]] [[funding-squeeze-breakout-g2-g1-g3]] [[funding-squeeze-breakout-g2-g2]] [[funding-squeeze-breakout-g2-g3]] [[funding-squeeze-breakout-g2-g4]] [[funding-squeeze-breakout-g4]] [[tmp-g2]] [[tmp-g4]] |
| `tsmom` | Time-series momentum: segno del rendimento su lookback. Base delle strategie trend-following. | [[commodities-cot-trend-v1]] [[commodities-trend-v1]] [[crypto-trend-flow-v1]] [[lux-0.1-beta]] [[lux-confluence-rr2-v1]] [[lux-flow-confluence-v1]] [[lux-nw-tsmom-v1]] [[lux-regime-3leg-v1]] [[lux-triple-3orthogonal-v1]] [[tsmom-aggressive-v1]] [[tsmom-atr-v1]] [[tsmom-conservative-v1]] [[tsmom-liq-v1]] [[tsmom-v1]] |
| `vol_compression` | Volatilità schiacciata che precede un'espansione. Setup neutro: serve un regime/catalizzatore per diventare direzionale. | [[funding-squeeze-breakout-g1]] [[funding-squeeze-breakout-g2-g1]] [[funding-squeeze-breakout-g2-g1-g1]] [[funding-squeeze-breakout-g2-g1-g2]] [[funding-squeeze-breakout-g2-g1-g3]] [[funding-squeeze-breakout-g2-g4]] [[tmp-g1]] |
| `volume_profile` | **TODO: definire** (segnale nuovo, non in glossario) | [[volprofile-reversion-v1]] |
| `volume_surge` | **TODO: definire** (segnale nuovo, non in glossario) | [[vol-expansion-breakout-v1]] |
| `vwap_zscore` | Distanza del prezzo dal VWAP in z-score. |z| basso (≤1σ) su altcoin high-beta = sotto soglia di edge (vedi lezioni). | [[index-meanrev-v1]] [[vwap-reversion-v1]] |
| `xsection_momentum` | **TODO: definire** (segnale nuovo, non in glossario) | [[lux-triple-3orthogonal-v1]] [[xsmom-v1]] |
