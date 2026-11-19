import { describe, expect, it } from 'vitest';

import { createTurnTrace } from '../e2eTurnTrace';

function steppedClock(start: number): { now: () => number; at: (ms: number) => void } {
  let current = start;
  return {
    now: () => current,
    at: (ms: number) => {
      current = ms;
    },
  };
}

describe('createTurnTrace', () => {
  it('records each event relative to the moment the trace started', () => {
    const clock = steppedClock(1_000);
    const trace = createTurnTrace(clock.now);
    clock.at(1_500);
    trace.recordEvent('routing_decision');
    clock.at(1_700);
    trace.recordEvent('tools_snapshot');

    expect(trace.snapshot().events).toEqual([
      { type: 'routing_decision', atMs: 500, lastAtMs: 500, count: 1 },
      { type: 'tools_snapshot', atMs: 700, lastAtMs: 700, count: 1 },
    ]);
  });

  it('folds consecutive events of one type into one entry with its first and last time', () => {
    const clock = steppedClock(0);
    const trace = createTurnTrace(clock.now);
    for (const at of [100, 150, 220]) {
      clock.at(at);
      trace.recordEvent('message');
    }
    clock.at(300);
    trace.recordEvent('message_end');
    clock.at(400);
    trace.recordEvent('message');

    expect(trace.snapshot().events).toEqual([
      { type: 'message', atMs: 100, lastAtMs: 220, count: 3 },
      { type: 'message_end', atMs: 300, lastAtMs: 300, count: 1 },
      { type: 'message', atMs: 400, lastAtMs: 400, count: 1 },
    ]);
  });

  it('keeps the first and the last entries and counts the ones dropped in between', () => {
    const clock = steppedClock(0);
    const trace = createTurnTrace(clock.now, 3);
    const types = ['a', 'b', 'a', 'b', 'a', 'b', 'a', 'b'];
    types.forEach((type, index) => {
      clock.at((index + 1) * 10);
      trace.recordEvent(type);
    });

    const snapshot = trace.snapshot();
    expect(snapshot.events.map((entry) => entry.atMs)).toEqual([10, 20, 30, 60, 70, 80]);
    expect(snapshot.dropped).toBe(2);
  });

  it('folds into the newest entry also after the head is full and the tail has started', () => {
    const clock = steppedClock(0);
    const trace = createTurnTrace(clock.now, 2);
    for (const [at, type] of [
      [10, 'a'],
      [20, 'b'],
      [30, 'c'],
      [40, 'c'],
    ] as const) {
      clock.at(at);
      trace.recordEvent(type);
    }

    expect(trace.snapshot().events).toEqual([
      { type: 'a', atMs: 10, lastAtMs: 10, count: 1 },
      { type: 'b', atMs: 20, lastAtMs: 20, count: 1 },
      { type: 'c', atMs: 30, lastAtMs: 40, count: 2 },
    ]);
    expect(trace.snapshot().dropped).toBe(0);
  });

  it('has no settle until the send ends, then keeps the first outcome only', () => {
    const clock = steppedClock(100);
    const trace = createTurnTrace(clock.now);
    expect(trace.snapshot().settle).toBeNull();

    clock.at(900);
    trace.recordSettle('resolved');
    clock.at(950);
    trace.recordSettle('rejected:late');

    expect(trace.snapshot().settle).toEqual({ atMs: 800, outcome: 'resolved' });
  });

  it('hands out snapshots that later events do not change', () => {
    const clock = steppedClock(0);
    const trace = createTurnTrace(clock.now);
    clock.at(10);
    trace.recordEvent('message');
    const before = trace.snapshot();
    clock.at(20);
    trace.recordEvent('message');
    trace.recordEvent('message_end');

    expect(before.events).toEqual([{ type: 'message', atMs: 10, lastAtMs: 10, count: 1 }]);
  });
});
