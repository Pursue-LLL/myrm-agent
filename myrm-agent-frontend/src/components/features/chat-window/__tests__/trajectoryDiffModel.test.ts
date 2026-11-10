import { describe, expect, it } from 'vitest';

import { findDivergence, turnStartIndexes } from '../trajectoryDiffModel';
import { step, trajectory, turn } from './trajectoryKit';

const session = (...turns: ReturnType<typeof turn>[]) => trajectory('s', null, turns);

describe('findDivergence', () => {
  it('finds nothing when both sessions ran alike, however they are cut into turns', () => {
    const a = session(turn('t1', 'p', [step('read', { path: 'a' }), step('edit')]));
    const b = session(turn('t1', 'p', [step('read', { path: 'a' })]), turn('t2', 'q', [step('edit')]));

    expect(findDivergence(a, b)).toBeNull();
  });

  it('finds nothing for two sessions without any tool call', () => {
    expect(findDivergence(session(turn('t', 'p', [])), session())).toBeNull();
  });

  it('points at the first step that uses another tool, counted over all turns', () => {
    const a = session(turn('t1', 'p', [step('read'), step('grep')]), turn('t2', 'q', [step('edit'), step('test')]));
    const b = session(turn('t1', 'p', [step('read'), step('grep')]), turn('t2', 'q', [step('edit'), step('build')]));

    expect(findDivergence(a, b)).toBe(3);
  });

  it('points at the first step with other arguments', () => {
    const a = session(turn('t1', 'p', [step('read', { path: 'a' }), step('read', { path: 'b' })]));
    const b = session(turn('t1', 'p', [step('read', { path: 'a' }), step('read', { path: 'c' })]));

    expect(findDivergence(a, b)).toBe(1);
  });

  it('compares arguments by content: key order and nesting order inside objects do not matter', () => {
    const a = session(turn('t1', 'p', [step('write', { path: 'a', options: { mode: 'x', retries: 2 } })]));
    const b = session(turn('t1', 'p', [step('write', { options: { retries: 2, mode: 'x' }, path: 'a' })]));

    expect(findDivergence(a, b)).toBeNull();
  });

  it('still tells arrays in another order apart', () => {
    const a = session(turn('t1', 'p', [step('open', { files: ['a', 'b'] })]));
    const b = session(turn('t1', 'p', [step('open', { files: ['b', 'a'] })]));

    expect(findDivergence(a, b)).toBe(0);
  });

  it('points at the first step the shorter session does not have, from either side', () => {
    const long = session(turn('t1', 'p', [step('read'), step('edit'), step('test')]));
    const short = session(turn('t1', 'p', [step('read'), step('edit')]));

    expect(findDivergence(long, short)).toBe(2);
    expect(findDivergence(short, long)).toBe(2);
  });

  it('prefers a difference inside the shared part over a difference in length', () => {
    const a = session(turn('t1', 'p', [step('read'), step('edit')]));
    const b = session(turn('t1', 'p', [step('grep'), step('edit'), step('test')]));

    expect(findDivergence(a, b)).toBe(0);
  });
});

describe('turnStartIndexes', () => {
  it('gives the position of each turn first step among all steps', () => {
    const turns = [
      turn('t1', 'p', [step('a'), step('b')]),
      turn('t2', 'q', []),
      turn('t3', 'r', [step('c')]),
      turn('t4', 's', [step('d')]),
    ];

    expect(turnStartIndexes(turns)).toEqual([0, 2, 2, 3]);
  });

  it('is empty without turns', () => {
    expect(turnStartIndexes([])).toEqual([]);
  });
});
