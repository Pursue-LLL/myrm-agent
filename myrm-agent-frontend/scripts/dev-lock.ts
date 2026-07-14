/**
 * [INPUT]
 * - port-cleanup::listPidsOnPort (POS: :3000 LISTEN PID discovery)
 * - port-cleanup::killListenersOnPort (POS: LISTEN-only port cleanup)
 *
 * [OUTPUT]
 * - DevLockRecord persistence in `.next/dev-server.lock`
 * - evaluateDevServerHealth / isDevServerHealthy / tryAttachToHealthyDevServer
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

function resolveNextDistDir(): string {
  const override = process.env.MYRM_NEXT_DIST_DIR?.trim();
  if (override) {
    return path.isAbsolute(override) ? override : path.join(process.cwd(), override);
  }
  return path.join(process.cwd(), '.next');
}

const LOCK_DIR = resolveNextDistDir();
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

function isLockAncestorOfPid(
  lockPid: number,
  pid: number,
  getParentPid: (pid: number) => number | null,
  maxDepth = 8,
): boolean {
  let current = pid;
  for (let depth = 0; depth < maxDepth; depth += 1) {
    if (current === lockPid) return true;
    const ppid = getParentPid(current);
    if (ppid === null || ppid <= 1) return false;
    current = ppid;
  }
  return false;
}

/** Lock supervisor owns LISTEN when it is the listener or an ancestor of the listener (spawn chain). */
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
    return Number.isFinite(n) && isLockAncestorOfPid(lockPid, n, getParentPid);
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

function isDevHttpResponsive(port: number): boolean {
  try {
    execSync(`curl -sf --max-time 3 http://127.0.0.1:${port}/`, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function writeDevLockRecord(port: number, pid: number, prior?: DevLockRecord | null): void {
  fs.mkdirSync(LOCK_DIR, { recursive: true });
  const record: DevLockRecord = {
    pid,
    port,
    cwd: prior?.cwd ?? process.cwd(),
    startedAt: prior?.startedAt ?? new Date().toISOString(),
  };
  fs.writeFileSync(LOCK_FILE, `${JSON.stringify(record, null, 2)}\n`, 'utf8');
}

/** Attach to an already-serving :port dev server instead of killing listeners (parallel ensure safe). */
export function tryAttachToHealthyDevServer(port: number): boolean {
  if (!isDevHttpResponsive(port)) {
    return false;
  }

  const listeners = listPidsOnPort(port);
  if (listeners.length === 0) {
    return false;
  }

  const lock = readDevLock();
  if (
    lock &&
    isProcessAlive(lock.pid) &&
    evaluateDevServerHealth(lock, port, listeners, isProcessAlive)
  ) {
    return true;
  }

  const adopted = Number.parseInt(listeners[0], 10);
  if (!Number.isFinite(adopted)) {
    return false;
  }

  writeDevLockRecord(port, adopted, lock);
  console.log(`✅ Adopted healthy dev listener PID ${adopted} on :${port}`);
  return true;
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

/** Refuse when another dev-server.lock owner is alive and healthy. */
export function assertDevLockAvailable(port: number): void {
  const existing = readDevLock();
  if (!existing || existing.pid === process.pid) return;

  if (!isProcessAlive(existing.pid)) {
    if (tryAttachToHealthyDevServer(port)) {
      return;
    }
    fs.unlinkSync(LOCK_FILE);
    return;
  }

  const listeners = listPidsOnPort(existing.port);
  if (evaluateDevServerHealth(existing, port, listeners, isProcessAlive)) {
    console.error(`❌ Dev server already running (PID ${existing.pid}, port ${existing.port})`);
    console.error(`   Started: ${existing.startedAt}`);
    console.error(`   CWD: ${existing.cwd}`);
    console.error('   Parallel attach: ./myrm ready --attach');
    console.error('   Reset stack: ./myrm stop && ./myrm ready');
    process.exit(1);
  }

  const reason =
    listeners.length === 0
      ? `PID ${existing.pid} alive but :${existing.port} not listening`
      : `PID ${existing.pid} alive but does not own LISTEN on :${existing.port}`;
  if (tryAttachToHealthyDevServer(port)) {
    return;
  }
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
