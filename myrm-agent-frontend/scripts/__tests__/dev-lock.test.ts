// @vitest-environment node
import { describe, expect, it } from 'vitest';

import {
  evaluateDevServerHealth,
  lockOwnsPortListeners,
  type DevLockRecord,
} from '../dev-lock';

const lock: DevLockRecord = {
  pid: 4242,
  port: 3000,
  cwd: '/tmp/frontend',
  startedAt: '2026-07-10T00:00:00.000Z',
};

describe('lockOwnsPortListeners', () => {
  it('returns true when lock pid is the listener', () => {
    expect(lockOwnsPortListeners(4242, ['4242'], () => null)).toBe(true);
  });

  it('returns true when listener parent is lock supervisor', () => {
    expect(lockOwnsPortListeners(4242, ['9001'], (pid) => (pid === 9001 ? 4242 : null))).toBe(
      true,
    );
  });

  it('returns false when foreign process listens', () => {
    expect(lockOwnsPortListeners(4242, ['9001'], () => 1)).toBe(false);
  });

  it('returns false when no listeners', () => {
    expect(lockOwnsPortListeners(4242, [], () => null)).toBe(false);
  });
});

describe('evaluateDevServerHealth', () => {
  it('returns true when lock supervisor owns child listener', () => {
    expect(
      evaluateDevServerHealth(
        lock,
        3000,
        ['9001'],
        (pid) => pid === 4242,
        (pid) => (pid === 9001 ? 4242 : null),
      ),
    ).toBe(true);
  });

  it('returns false when another process listens on port', () => {
    expect(
      evaluateDevServerHealth(lock, 3000, ['9999'], (pid) => pid === 4242, () => 1),
    ).toBe(false);
  });

  it('returns false when lock pid is not alive', () => {
    expect(evaluateDevServerHealth(lock, 3000, ['4242'], () => false)).toBe(false);
  });

  it('returns false when lock port mismatches', () => {
    expect(
      evaluateDevServerHealth(lock, 3001, ['4242'], (pid) => pid === 4242),
    ).toBe(false);
  });

  it('returns false when lock is null', () => {
    expect(evaluateDevServerHealth(null, 3000, ['4242'], () => true)).toBe(false);
  });
});
