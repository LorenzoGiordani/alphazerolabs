import assert from "node:assert/strict";
import test from "node:test";

import worker, { dispatch, isRomeMakerTime, workflowsForCron } from "./index.js";


test("routes deterministic and checker schedules", () => {
  assert.deepEqual(
    workflowsForCron("10 * * * *", 0),
    ["paper-run.yml", "propr-competition.yml", "hl-snapshot.yml", "research-checker.yml"],
  );
  assert.equal(workflowsForCron("*/3 * * * *", 0), null);
  assert.deepEqual(
    workflowsForCron("30 5 * * *", 0),
    ["kronos-precompute.yml", "xsection-precompute.yml"],
  );
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

test("dispatch retries transient failures and then succeeds", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return calls < 3
      ? { status: 503, text: async () => "temporary" }
      : { status: 204, text: async () => "" };
  };
  try {
    assert.equal(await dispatch({ GH_PAT: "test" }, "propr-competition.yml"), true);
    assert.equal(calls, 3);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("dispatch rejects after three failed attempts", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return { status: 500, text: async () => "failed" };
  };
  try {
    await assert.rejects(
      dispatch({ GH_PAT: "test" }, "propr-competition.yml"),
      /failed after 3 attempts/,
    );
    assert.equal(calls, 3);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("dispatch retries network errors", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    if (calls < 3) throw new TypeError("network unavailable");
    return { status: 204, text: async () => "" };
  };
  try {
    assert.equal(await dispatch({ GH_PAT: "test" }, "propr-competition.yml"), true);
    assert.equal(calls, 3);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
