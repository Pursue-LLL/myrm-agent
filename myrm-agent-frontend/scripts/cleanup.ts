import { execSync } from 'child_process';
import { basename, dirname, join, resolve } from 'path';
import { readdirSync, rmSync, statSync, truncateSync } from 'fs';
import { clearDevLock, clearStaleDevLock } from './dev-lock';
import { APP_DEV_PORT, killListenersOnPort, listPidsOnPort } from './port-cleanup';

const ROOT = join(import.meta.dir, '..');

function resolveActiveIsolatedDirName(): string | null {
  const explicit = process.env.MYRM_NEXT_DIST_DIR?.trim();
  if (explicit) {
    return basename(explicit);
  }
  const home = process.env.HOME ?? '';
  const defaultStateDir = join(home, '.local/state/myrm-dev');
  const stateDir = process.env.MYRM_DEV_STATE_DIR ?? defaultStateDir;
  if (resolve(stateDir) !== resolve(defaultStateDir)) {
    const runtimeNs = (process.env.MYRM_RUNTIME_NAMESPACE ?? basename(dirname(stateDir))).replace(
      /[^a-zA-Z0-9_.-]/g,
      '-',
    );
    return `.next-isolated-${runtimeNs}`;
  }
  return null;
}

console.log(`🧹 Cleaning up myrm-agent-frontend dev port :${APP_DEV_PORT} only...\n`);

if (clearStaleDevLock()) {
  console.log('🗑️  Removed stale dev-server.lock\n');
}
clearDevLock();

function showPortProcesses(port: number) {
  const pidList = listPidsOnPort(port);
  if (pidList.length === 0) {
    console.log(`✅ Port ${port} is free.\n`);
    return;
  }
  console.log(`Found ${pidList.length} process(es) on port ${port}:`);
  pidList.forEach((pid) => {
    try {
      const info = execSync(`ps -p ${pid} -o pid,ppid,%cpu,%mem,etime,command | tail -1`, {
        encoding: 'utf-8',
      }).trim();
      console.log(`  ${info}`);
    } catch {
      console.log(`  PID: ${pid}`);
    }
  });
  console.log('');
}

showPortProcesses(APP_DEV_PORT);
const cleanedCount = killListenersOnPort(APP_DEV_PORT, true);

console.log('📊 Current memory usage:');
try {
  console.log(execSync('vm_stat | head -5', { encoding: 'utf-8' }));
} catch {
  // ignore
}

console.log(`\n✨ Cleanup complete! Terminated ${cleanedCount} process(es) on :${APP_DEV_PORT}.`);
console.log('ℹ️  Other ports (e.g. myrm-website :3002) are untouched.');

function cleanIsolatedNextDirs(): number {
  const activeName = resolveActiveIsolatedDirName();
  let removed = 0;
  for (const entry of readdirSync(ROOT)) {
    if (!entry.startsWith('.next-isolated-')) continue;
    if (activeName && entry === activeName) continue;
    const target = join(ROOT, entry);
    try {
      rmSync(target, { recursive: true, force: true });
      removed += 1;
    } catch {
      // ignore single-dir failures
    }
  }
  return removed;
}

function truncateDevLogs(): number {
  const logNames = ['.myrm-dev-frontend.log', '.myrm-dev-frontend-fg.log'];
  let truncated = 0;
  for (const name of logNames) {
    const logPath = join(ROOT, name);
    try {
      if (statSync(logPath).size > 0) {
        truncateSync(logPath, 0);
        truncated += 1;
      }
    } catch {
      // missing log is fine
    }
  }
  return truncated;
}

const isolatedRemoved = cleanIsolatedNextDirs();
if (isolatedRemoved > 0) {
  console.log(`🗑️  Removed ${isolatedRemoved} stale .next-isolated-* director(ies).\n`);
}

const logsTruncated = truncateDevLogs();
if (logsTruncated > 0) {
  console.log(`📝 Truncated ${logsTruncated} dev log file(s).\n`);
}

const lockPath = join(ROOT, 'package-lock.json');
try {
  if (statSync(lockPath).isFile()) {
    rmSync(lockPath);
    console.log('🗑️  Removed stray package-lock.json (bun.lock is SSOT).\n');
  }
} catch {
  // absent is expected
}
