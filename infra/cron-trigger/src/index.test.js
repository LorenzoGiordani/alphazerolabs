import assert from "node:assert/strict";
import test from "node:test";

import worker from "./index.js";


test("does not expose an unauthenticated HTTP dispatch handler", () => {
  assert.equal(worker.fetch, undefined);
});

test("scheduled handler performs no network or workflow dispatch", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("network call from dormant Worker");
  };
  const tasks = [];
  try {
    await worker.scheduled({}, {}, { waitUntil: (task) => tasks.push(task) });
    await Promise.all(tasks);
    assert.equal(tasks.length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
