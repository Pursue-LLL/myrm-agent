/**
 * [INPUT]
 * - port-cleanup::listPidsOnPort (POS: :3000 LISTEN PID discovery)
 * - port-cleanup::killListenersOnPort (POS: LISTEN-only port cleanup)
 *
 * [OUTPUT]
 * - DevLockRecord persistence in `.next/dev-server.lock`
 * - evaluateDevServerHealth / isDevServerHealthy: dev-server ownership checks
 * - assertDevLockAvailable / acquireDevLock / releaseDevLock
 *
 * [POS]
 * Frontend dev-server lock and health gate. Prevents parallel `bun run dev` from
 * killing a healthy Next.js listener; lock.pid is the dev.ts supervisor (child may LISTEN).
 */
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

import { killListenersOnPort, listPidsOnPort } from './port-cleanup';

const LOCK_DIR = path.join(process.cwd(), '.next');
const LOCK_FILE = path.join(LOCK_DIR, 'dev-server.lock');

export interface DevLockRecord {
  pid: number;
  port: number;
  cwd: string;
  startedAt: string;
}

function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function readParentPid(pid: number): number | null {
  try {
    const out = execSync(`ps -p ${pid} -o ppid=`, { encoding: 'utf-8' }).trim();
    const ppid = Number.parseInt(out, 10);
    return Number.isFinite(ppid) ? ppid : null;
  } catch {
    return null;
  }
}

/** Lock supervisor owns LISTEN when it is the listener or the listener's parent (spawned Next). */
export function lockOwnsPortListeners(
  lockPid: number,
  listenerPids: readonly string[],
  getParentPid: (pid: number) => number | null = readParentPid,
): boolean {
  if (listenerPids.length === 0) return false;
  const lockStr = String(lockPid);
  if (listenerPids.includes(lockStr)) return true;
  return listenerPids.some((listenerPid) => {
    const n = Number.parseInt(listenerPid, 10);
    return Number.isFinite(n) && getParentPid(n) === lockPid;
  });
}

export function readDevLock(): DevLockRecord | null {
  if (!fs.existsSync(LOCK_FILE)) return null;
  try {
    const raw = fs.readFileSync(LOCK_FILE, 'utf8');
    const parsed = JSON.parse(raw) as DevLockRecord;
    if (typeof parsed.pid !== 'number' || typeof parsed.port !== 'number') return null;
    return parsed;
  } catch {
    return null;
  }
}

function removeDevLockIfOwned(): void {
  const lock = readDevLock();
  if (lock?.pid === process.pid) {
    fs.unlinkSync(LOCK_FILE);
  }
}

/** Pure health check: lock supervisor alive and owns :port LISTEN (directly or via child). */
export function evaluateDevServerHealth(
  lock: DevLockRecord | null,
  port: number,
  listenerPids: readonly string[],
  pidAlive: (pid: number) => boolean,
  getParentPid: (pid: number) => number | null = readParentPid,
): boolean {
  if (!lock || lock.port !== port) return false;
  if (!pidAlive(lock.pid)) return false;
  return lockOwnsPortListeners(lock.pid, listenerPids, getParentPid);
}

export function isDevServerHealthy(port: number): boolean {
  const lock = readDevLock();
  return evaluateDevServerHealth(lock, port, listPidsOnPort(port), isProcessAlive);
}

function reclaimStaleDevLock(existing: DevLockRecord, port: number, reason: string): void {
  console.warn(`⚠️  Stale dev lock: ${reason} — reclaiming`);
  try {
    process.kill(existing.pid, 'SIGTERM');
  } catch {
    // already gone
  }
  killListenersOnPort(port, true);
  fs.unlinkSync(LOCK_FILE);
}

/** Refuse when another dev-server.lock owner is alive; MYRM_DEV_FORCE=1 takes over. */
export function assertDevLockAvailable(port: number): void {
  const existing = readDevLock();
  if (!existing || existing.pid === process.pid) return;

  if (!isProcessAlive(existing.pid)) {
    fs.unlinkSync(LOCK_FILE);
    return;
  }

  const listeners = listPidsOnPort(existing.port);
  if (evaluateDevServerHealth(existing, port, listeners, isProcessAlive)) {
    const force = process.env.MYRM_DEV_FORCE === '1' || process.env.MYRM_DEV_FORCE === 'true';
    if (!force) {
      console.error(`❌ Dev server already running (PID ${existing.pid}, port ${existing.port})`);
      console.error(`   Started: ${existing.startedAt}`);
      console.error(`   CWD: ${existing.cwd}`);
      console.error('   Stop it first, or run: MYRM_DEV_FORCE=1 bun run dev');
      process.exit(1);
    }
    console.warn(`⚠️  MYRM_DEV_FORCE=1 — stopping previous dev server PID ${existing.pid}`);
    try {
      process.kill(existing.pid, 'SIGTERM');
    } catch {
      // already gone
    }
    killListenersOnPort(port, true);
    return;
  }

  const reason =
    listeners.length === 0
      ? `PID ${existing.pid} alive but :${existing.port} not listening`
      : `PID ${existing.pid} alive but does not own LISTEN on :${existing.port}`;
  reclaimStaleDevLock(existing, port, reason);
}

/** Write lock after port is free and before spawning Next.js. */
export function acquireDevLock(port: number): void {
  assertDevLockAvailable(port);

  fs.mkdirSync(LOCK_DIR, { recursive: true });
  const record: DevLockRecord = {
    pid: process.pid,
    port,
    cwd: process.cwd(),
    startedAt: new Date().toISOString(),
  };
  fs.writeFileSync(LOCK_FILE, `${JSON.stringify(record, null, 2)}\n`, 'utf8');
}

export function releaseDevLock(): void {
  try {
    removeDevLockIfOwned();
  } catch {
    // ignore
  }
}

export function clearStaleDevLock(): boolean {
  const lock = readDevLock();
  if (!lock) return false;
  if (isProcessAlive(lock.pid)) return false;
  fs.unlinkSync(LOCK_FILE);
  return true;
}

/** Remove lock file unconditionally (used by bun run cleanup). */
export function clearDevLock(): void {
  try {
    if (fs.existsSync(LOCK_FILE)) fs.unlinkSync(LOCK_FILE);
  } catch {
    // ignore
  }
}
