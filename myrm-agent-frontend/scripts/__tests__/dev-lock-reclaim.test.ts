// @vitest-environment node
import fs from 'fs';
import os from 'os';
import path from 'path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { exitsWithin, freePort, startProcess, stopAllProcesses } from './helpers/process-fixtures';

const HTTP_LISTENER = `
  require('http')
    .createServer((_req, res) => res.end('ok'))
    .listen(Number(process.argv[1]), '127.0.0.1', () => console.log('ready'));
`;
const SLEEPER = 'setTimeout(() => {}, 30000)';

let distDir: string;

function writeLock(pid: number, port: number): void {
  fs.writeFileSync(
    path.join(distDir, 'dev-server.lock'),
    JSON.stringify({ pid, port, cwd: '/tmp', startedAt: '2020-01-01T00:00:00.000Z' }),
  );
}

async function loadDevLock() {
  // The lock path is resolved when the module loads.
  vi.resetModules();
  return import('../dev-lock');
}

describe('dev lock never takes over or signals what this dev server did not start', () => {
  beforeEach(() => {
    distDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dev-lock-reclaim-'));
    vi.stubEnv('MYRM_NEXT_DIST_DIR', distDir);
    vi.stubEnv('MYRM_RUNTIME_NAMESPACE', 'shared');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    stopAllProcesses();
    fs.rmSync(distDir, { recursive: true, force: true });
  });

  it('does not adopt a healthy listener stamped by another runtime as its own dev server', async () => {
    const port = await freePort();
    await startProcess(HTTP_LISTENER, [String(port)], 'user');
    const { tryAttachToHealthyDevServer } = await loadDevLock();
    expect(tryAttachToHealthyDevServer(port)).toBe(false);
    expect(fs.existsSync(path.join(distDir, 'dev-server.lock'))).toBe(false);
  });

  it('adopts a healthy listener this runtime started', async () => {
    const port = await freePort();
    const own = await startProcess(HTTP_LISTENER, [String(port)], 'shared');
    const { tryAttachToHealthyDevServer } = await loadDevLock();
    expect(tryAttachToHealthyDevServer(port)).toBe(true);
    expect(JSON.parse(fs.readFileSync(path.join(distDir, 'dev-server.lock'), 'utf8')).pid).toBe(own.pid);
  });

  it.each([
    ['stamped by another runtime', 'user'],
    ['un-stamped and unrelated to this frontend', null],
  ])('does not signal a stale lock pid that is %s', async (_label, namespace) => {
    const port = await freePort();
    const recycled = await startProcess(SLEEPER, [], namespace, { printsReady: false });
    writeLock(recycled.pid as number, port);
    const { assertDevLockAvailable } = await loadDevLock();
    assertDevLockAvailable(port);
    expect(await exitsWithin(recycled, 1500)).toBe(false);
    expect(fs.existsSync(path.join(distDir, 'dev-server.lock'))).toBe(false);
  });

  it("still stops a stale lock pid that is this runtime's own dev server", async () => {
    const port = await freePort();
    const own = await startProcess(SLEEPER, [], 'shared', { printsReady: false });
    writeLock(own.pid as number, port);
    const { assertDevLockAvailable } = await loadDevLock();
    assertDevLockAvailable(port);
    expect(await exitsWithin(own, 5000)).toBe(true);
    expect(own.signalCode).toBe('SIGTERM');
  });
});
