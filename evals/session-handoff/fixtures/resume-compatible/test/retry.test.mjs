import assert from 'node:assert/strict';
import test from 'node:test';

import { retry } from '../src/retry.ts';

test('retries a transient failure', async () => {
  let calls = 0;
  const result = await retry(async () => {
    calls += 1;
    if (calls < 3) {
      throw new Error('transient');
    }
    return 'ok';
  }, 3);

  assert.equal(result, 'ok');
  assert.equal(calls, 3);
});

test('stops after the configured number of attempts', async () => {
  let calls = 0;
  await assert.rejects(
    retry(async () => {
      calls += 1;
      throw new Error('persistent');
    }, 2),
    /persistent/,
  );
  assert.equal(calls, 2);
});
