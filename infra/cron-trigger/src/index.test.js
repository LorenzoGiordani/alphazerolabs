import assert from "node:assert/strict";
import test from "node:test";

import worker, { isRomeMakerTime, workflowsForCron } from "./index.js";


test("routes deterministic and checker schedules", () => {
  assert.deepEqual(
    workflowsForCron("10 * * * *", 0),
    ["paper-run.yml", "hl-snapshot.yml", "research-checker.yml"],
  );
  assert.equal(workflowsForCron("*/3 * * * *", 0), null);
});

test("dispatches maker at 07:15 Rome across DST", () => {
  assert.equal(isRomeMakerTime(Date.parse("2026-01-14T06:15:00Z")), true);
  assert.equal(isRomeMakerTime(Date.parse("2026-01-14T05:15:00Z")), false);
  assert.equal(isRomeMakerTime(Date.parse("2026-07-14T05:15:00Z")), true);
  assert.equal(isRomeMakerTime(Date.parse("2026-07-14T06:15:00Z")), false);
});

test("does not expose an unauthenticated HTTP dispatch handler", () => {
  assert.equal(worker.fetch, undefined);
});
