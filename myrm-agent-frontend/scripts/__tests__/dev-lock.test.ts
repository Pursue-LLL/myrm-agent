// @vitest-environment node
import { spawnSync } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';

import { afterEach, describe, expect, it } from 'vitest';

import {
  evaluateDevServerHealth,
  isDistDirInUse,
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

  it('returns true when listener is grandchild of lock supervisor (bun→node→next)', () => {
    const parentChain: Record<number, number> = {
      10355: 10354,
      10354: 10344,
      10344: 10341,
    };
    expect(
      lockOwnsPortListeners(10341, ['10355'], (pid) => parentChain[pid] ?? null),
    ).toBe(true);
  });

  it('returns false when foreign process listens', () => {
    expect(lockOwnsPortListeners(4242, ['9001'], () => 1)).toBe(false);
  });

  it('returns false when no listeners', () => {
    expect(lockOwnsPortListeners(4242, [], () => null)).toBe(false);
  });
});

describe('evaluateDevServerHealth', () => {
  it('returns true when lock supervisor owns grandchild listener', () => {
    const parentChain: Record<number, number> = {
      10355: 10354,
      10354: 10344,
      10344: 10341,
    };
    expect(
      evaluateDevServerHealth(
        { ...lock, pid: 10341 },
        3000,
        ['10355'],
        (pid) => pid === 10341,
        (pid) => parentChain[pid] ?? null,
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

describe('isDistDirInUse', () => {
  const dirs: string[] = [];
  const distWithLock = (content?: string): string => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dist-in-use-'));
    dirs.push(dir);
    if (content !== undefined) {
      fs.writeFileSync(path.join(dir, 'dev-server.lock'), content, 'utf8');
    }
    return dir;
  };
  const lockJson = (pid: number): string => JSON.stringify({ ...lock, pid });

  afterEach(() => {
    for (const dir of dirs.splice(0)) {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  it('is in use while the lock supervisor is alive', () => {
    expect(isDistDirInUse(distWithLock(lockJson(process.pid)))).toBe(true);
  });

  it('is free once the lock supervisor has exited', () => {
    const exited = spawnSync(process.execPath, ['-e', '0']);
    expect(isDistDirInUse(distWithLock(lockJson(exited.pid)))).toBe(false);
  });

  it('is free without a lock or with an unreadable one', () => {
    expect(isDistDirInUse(distWithLock())).toBe(false);
    expect(isDistDirInUse(distWithLock('not json'))).toBe(false);
    expect(isDistDirInUse(distWithLock('{"port":1}'))).toBe(false);
    expect(isDistDirInUse(path.join(os.tmpdir(), 'does-not-exist-dist'))).toBe(false);
  });
});
