# Strategy evidence contract

`status: champion` means **paper champion**, not execution or capital readiness.
Promotion and any external execution are fail-closed until two separate,
content-addressed records verify:

1. `manifests/<strategy-id>.json`, produced by the maker;
2. `checker/<strategy-id>.json`, produced by an independent checker run.

The maker manifest schema is version 1:

```json
{
  "schema_version": 1,
  "strategy_id": "example-v1",
  "strategy_logic_sha256": "64 lowercase hex characters",
  "maker_run_id": "maker-run-id",
  "dsr": {
    "value": 0.96,
    "artifact_path": "evidence/artifacts/example-v1-dsr.json",
    "artifact_sha256": "64 lowercase hex characters"
  },
  "oos": {
    "verdict": "PASS",
    "artifact_path": "evidence/artifacts/example-v1-oos.json",
    "artifact_sha256": "64 lowercase hex characters"
  }
}
```

The checker receipt schema is version 1:

```json
{
  "schema_version": 1,
  "strategy_id": "example-v1",
  "maker_run_id": "maker-run-id",
  "checker_run_id": "different-checker-run-id",
  "manifest_sha256": "sha256 of the exact maker manifest bytes",
  "verdict": "APPROVE_EVIDENCE_READY"
}
```

The verifier in `backtest/evidence.py` requires 0.95 ≤ DSR ≤ 1, OOS `PASS`,
matching artifact hashes, an exact manifest hash and distinct maker/checker IDs.
Absolute paths, path traversal, missing fields, malformed JSON, non-finite values
or any mismatch block promotion. Changing only lifecycle `status` preserves the
subject hash; every other strategy change requires fresh evidence.

No receipt in this directory authorizes real capital. That remains a separate,
explicit human decision.

## Evolution L2 evidence

`evidence/evolution/<strategy-id>/` is a separate admission trail for a new
paper challenger. It contains the exact approved L1 receipt, OpenRouter
`deepseek/deepseek-v4-pro` proposal and provider metadata, frozen parent snapshot,
L2 Maker record, independent review/provider metadata, replayed L2 Checker record,
and frozen-data manifest. The frozen dataset itself remains a 30-day GitHub
artifact; its exact hash and schema are recorded in the manifest.

Actions first emits a `HUMAN_PR_REQUIRED` publication bundle; an authenticated
Codex/human step creates the draft PR. A human merge is required before the
strategy becomes visible to the paper registry. Its tail split is a development
proxy, not the official holdout required by the champion evidence contract above.
An L2 receipt never authorizes Propr readiness, live orders, or capital.
For a newly added receipt, the PR validator also rechecks the current parent and
family challenger cap. Historical validation keeps the logic hash binding but
accepts later `champion`/`retired` lifecycle states and parent evolution. At runtime
the pinned L2 basket requires 100% signal coverage before paper-state or journal
mutation.

Portfolio strategies have two additional fail-closed boundaries. Runtime
heartbeats are autocorrelated and therefore never satisfy the automatic
trade-count promotion gate. The current Propr executor also applies a different
universe/risk overlay, so it stays blocked even when evidence is valid until an
independent execution-contract test proves it reproduces the hashed strategy.
