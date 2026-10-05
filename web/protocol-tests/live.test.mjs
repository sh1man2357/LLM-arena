import { test } from 'node:test';
import assert from 'node:assert/strict';
import { appendConfirmed, completeSnapshot } from '../src/live.ts';

const frame = seq => ({ seq, tick: seq ? seq-1 : null, state: { tick: seq }, events: [], calls: [], actions: [], visual: {} });
const initial = { attempt_id: 'first', frames: [frame(0), frame(1)], last_seq: 1, partial: true, result: null };
const delta = (frames, last_seq=3) => ({ ...initial, frames, last_seq });

test('ordered deltas and repeated confirmed frames preserve one sequence', () => {
  const value = appendConfirmed(initial, delta([frame(1), frame(2), frame(2), frame(3)]));
  assert.deepEqual(value.frames.map(f => f.seq), [0, 1, 2, 3]);
});
test('gaps, absent tail and conflicting duplicates require full recovery', () => {
  assert.equal(appendConfirmed(initial, delta([frame(3)])), undefined);
  assert.equal(appendConfirmed(initial, delta([frame(2)])), undefined);
  const changed = frame(1); changed.state.tick = 999;
  assert.equal(appendConfirmed(initial, delta([changed])), undefined);
});
test('new attempt cannot append even when its frame numbers coincide', () => {
  assert.equal(appendConfirmed(initial, { ...delta([frame(2)]), attempt_id: 'second' }), undefined);
  assert.equal(appendConfirmed(initial, { ...delta([frame(2)]), resync_required: true }), undefined);
});
test('full snapshots require the initial frame and declared complete sequence', () => {
  assert.equal(completeSnapshot(initial), true);
  assert.equal(completeSnapshot(delta([frame(1), frame(2)])), false);
  assert.equal(completeSnapshot({ ...initial, last_seq: 2 }), false);
});
