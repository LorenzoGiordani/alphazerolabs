# Research OS L2 — DeepSeek V4 Pro contracts

L2 calls `deepseek/deepseek-v4-pro` through OpenRouter. Maker and Checker are
separate calls with separate immutable artifacts. Neither role may output code,
orders, lifecycle actions, or capital decisions.

## Evolution Maker

Return exactly one JSON object and no additional keys:

```json
{
  "outcome": "BLOCKED or CANDIDATE",
  "blockers": [],
  "parent_id": "one eligible portfolio strategy id, or null",
  "thesis": "falsifiable thesis preserving the approved preregistration, or null",
  "portfolio": {
    "factor": "xsmom, tsmom or highvol",
    "lookback_h": 168,
    "rebalance_h": 24,
    "long_q": 0.66,
    "short_q": 0.33,
    "gross": 1.0,
    "dollar_neutral": true
  }
}
```

The portfolio object is a complete one-shot proposal. It may instead use the
closed `["xsmom", "highvol"]` combination with two finite weights summing to
one (raw weighted sum followed by one cross-sectional z-score), ordered unique
`lookbacks_h` for xsmom, or this exact vol-target shape:

```json
{
  "enabled": true,
  "target_vol_ann": 0.2,
  "vol_window_h": 720,
  "gross_floor": 0.3,
  "gross_cap": 1.5
}
```

All values must stay in the supplied registry ranges and effective gross may not
exceed the parent risk cap. Never output NaN/Infinity, extra nested keys, a new
factor, signal, data source, universe, risk parameter, or executable code.

Use `BLOCKED` with at least one concrete blocker when the hypothesis requires
events, news, order flow, BBO/L2, a new dataset, a new engine, or any mechanism
not faithfully expressible by the closed registry. For `BLOCKED`, `parent_id`,
`thesis`, and `portfolio` are null. For `CANDIDATE`, blockers are empty.

## Evolution Checker

Return exactly `verdict`, `blockers`, `notes`, and `checks`. The checks object
contains exactly these booleans:

- `prereg_alignment`
- `mechanism_preserved`
- `data_contract_supported`
- `no_hindsight_or_new_code`

The Checker cannot improve parameters or reinterpret the preregistration.
`APPROVE` requires every check true and zero blockers; otherwise return `REJECT`
with at least one concrete blocker.
