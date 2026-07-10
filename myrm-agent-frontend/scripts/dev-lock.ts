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

function isPortListening(port: number): boolean {
  return listPidsOnPort(port).length > 0;
}

/** Refuse when another dev-server.lock owner is alive; MYRM_DEV_FORCE=1 takes over. */
export function assertDevLockAvailable(port: number): void {
  const existing = readDevLock();
  if (!existing || existing.pid === process.pid) return;

  if (isProcessAlive(existing.pid)) {
    if (!isPortListening(existing.port)) {
      console.warn(
        `⚠️  Stale dev lock: PID ${existing.pid} alive but :${existing.port} not listening — reclaiming`,
      );
      try {
        process.kill(existing.pid, 'SIGTERM');
      } catch {
        // already gone
      }
      killListenersOnPort(port, true);
      fs.unlinkSync(LOCK_FILE);
      return;
    }
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

  fs.unlinkSync(LOCK_FILE);
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
