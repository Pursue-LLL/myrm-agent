// @vitest-environment node
import { spawn, type ChildProcess } from 'child_process';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { resolveCleanupPort } from '../cleanup-port';
import { filterOwnedPids } from '../cleanup-targets';

describe('resolveCleanupPort', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('targets the shared dev UI, never the user stack on 3000', () => {
    vi.stubEnv('MYRM_FRONTEND_PORT', '');
    vi.stubEnv('MYRM_SHARED_FRONTEND_PORT', '');
    expect(resolveCleanupPort()).toBe(23000);
  });

  it('follows the shared-port override and an explicit frontend port', () => {
    vi.stubEnv('MYRM_FRONTEND_PORT', '');
    vi.stubEnv('MYRM_SHARED_FRONTEND_PORT', '24000');
    expect(resolveCleanupPort()).toBe(24000);
    vi.stubEnv('MYRM_FRONTEND_PORT', '14001');
    expect(resolveCleanupPort()).toBe(14001);
  });
});

describe('filterOwnedPids', () => {
  const children: ChildProcess[] = [];
  const spawnStamped = (namespace: string): string => {
    // Not /bin/sleep: macOS hides the environment of platform binaries from `ps eww`.
    const child = spawn(process.execPath, ['-e', 'setTimeout(() => {}, 30000)'], {
      env: { ...process.env, MYRM_RUNTIME_NAMESPACE: namespace, MYRM_DEV_STATE_DIR: `/tmp/${namespace}` },
      stdio: 'ignore',
    });
    children.push(child);
    return String(child.pid);
  };

  afterEach(() => {
    for (const child of children.splice(0)) {
      child.kill('SIGKILL');
    }
  });

  it('keeps only processes stamped by the given runtime', () => {
    const shared = spawnStamped('shared');
    const user = spawnStamped('user');
    const isolated = spawnStamped('isolated-a1');
    expect(filterOwnedPids([shared, user, isolated], 'shared')).toEqual([shared]);
    expect(filterOwnedPids([shared, user, isolated], 'user')).toEqual([user]);
  });

  it('drops unstamped processes and survives an empty list', () => {
    expect(filterOwnedPids([String(process.pid)], 'shared')).toEqual([]);
    expect(filterOwnedPids([], 'shared')).toEqual([]);
  });
});
