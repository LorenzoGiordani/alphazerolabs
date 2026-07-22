# Research OS L2 — strategy evolution

L2 connects an independently approved Research OS preregistration to a human-
reviewed paper challenger. It is separate from `paper-run` and cannot merge,
trade live, or allocate capital.

```text
Research Maker L1
  → Research Checker L1 (one authoritative receipt)
  → evolution-intake: FIFO disposition, READY or REJECTED
  → Evolution Maker L2: DeepSeek V4 Pro via OpenRouter, one mutation or BLOCKED
  → frozen six-month hourly panel on a deterministic explicit basket
  → deterministic development/tail gate
  → Evolution Checker L2: separate DeepSeek V4 Pro call + exact replay
  → publication artifact: HUMAN_PR_REQUIRED
  → Codex/human authenticated push + draft PR
  → human merge
  → paper-run discovers the challenger
```

Artifacts are retained for 30 days. `evolution-intake.yml` is read-only and
disposes each authoritative Checker receipt exactly once. `evolution-run.yml`
processes the oldest READY intake. It never uses Z.AI: Maker and Checker L2 use
only `deepseek/deepseek-v4-pro` through `OPENROUTER_API_KEY` in separate jobs.

## One-shot and recovery contract

For each research pack there can be only one authoritative
`evolution-maker-<pack_id>` and one `evolution-checker-<pack_id>`. A retry looks
for these artifacts first and reuses their exact bytes. It must never ask the
model for a second mutation or semantic review after an authoritative artifact
exists. A failure before an artifact exists may retry that stage; no backtest
trial has yet been admitted.

A deterministic rejection creates `evolution-final-<pack_id>`. Approval creates
an `evolution-publication-<pack_id>` bundle and a final status
`HUMAN_PR_REQUIRED`. GitHub Actions has read-only repository permissions and does
not push or open a PR. This matches the current repository setting, which does
not permit `GITHUB_TOKEN` to create pull requests. Codex or a human downloads the
publication bundle, reruns `validate-published`, then uses normal authenticated
Git/GitHub credentials to push a branch and open a draft PR.

## V1 capability boundary

V1 can mutate only active `engine: portfolio` parents expressible with the closed
`xsmom`, `tsmom`, and `highvol` registry. A family at the existing active-
challenger cap is not eligible. The cap is checked again against the publication
registry and by PR CI, so concurrent publications cannot overfill a family. The
model cannot add code, signals, data, universe rules, or risk fields. Nested
parameters, finite numeric types, booleans,
vol-target shape, and effective gross versus the parent leverage cap are checked
strictly around the older permissive validator.

The candidate does not inherit a drifting `all_perps` resolver. L2 deterministically
pins the parent's declared `paper_symbols` as an explicit candidate basket, bounded
by `risk.max_concurrent_positions`. Parent and candidate are evaluated on that same
basket; the model cannot choose or change it. The runtime verifies the basket hash
and requires signal coverage for every pinned symbol before mark-to-market,
rebalance, state, or journal mutation. The legacy 80% signal threshold does not
apply to L2 challengers.

The frozen panel must contain every declared symbol, at least 180 days of continuous
hourly positive finite prices, a unique ordered timestamp index, and no silent source
drop. The Maker sees the preregistration and eligible parent inventory but not this
new backtest. Event studies, order flow, BBO/L2, new datasets, and new engines must
return `BLOCKED`; they are never approximated with candles.

## Deterministic admission gates

All gates must pass:

- at least 720 hourly tail observations;
- positive full-period Sharpe;
- DSR at least 0.95, counting the existing strategy inventory as prior trials;
- positive tail return;
- tail drawdown no worse than -30%;
- tail Sharpe at least 0.10 above the parent;
- at least 12 rebalances;
- independent semantic review with all checks true and zero blockers.

The last third of the panel is labelled
`development-tail-oos-proxy-not-official-holdout`. It is a challenger admission
screen, not official OOS/forward proof, Propr readiness, or permission to fund.
Parent and candidate use the same timestamp boundary; warmup is excluded
explicitly and economic zero-return hours remain in the statistics.

## Durable PR evidence

An approved publication contains the candidate YAML plus exact L1 receipt, L2
proposal/provider metadata, frozen parent snapshot, Maker record, independent
review/provider metadata, Checker record, and data manifest. Publication is
create-once: an existing path with different bytes stops the operation.

`integrity-ci.yml` runs historical lineage validation on every evolution receipt,
then applies a strict admission check to evidence directories newly added by the
PR. Historical validation permits only the normal child lifecycle transitions
`challenger → champion/retired` while keeping the signed strategy logic immutable.
The new-admission check additionally verifies current parent status, the family cap,
and stable parent execution/risk/universe fields. A draft PR whose parent changed,
retired, or whose family filled concurrently cannot merge on stale evidence; later
legitimate lifecycle changes do not invalidate its historical receipt.
