/**
 * [INPUT]
 * - cleanup-port::resolveCleanupPort (POS: the shared dev UI port)
 * - cleanup-targets::filterOwnedPids (POS: what cleanup may touch — own stamped processes)
 * - port-cleanup::listPidsOnPort (POS: LISTEN PID discovery)
 * - dev-lock::isDistDirInUse (POS: dev-server lock gate)
 * - frontend_dev_pause.py write (POS: shared pause stamp, 8h default)
 *
 * [OUTPUT]
 * - Shared dev UI cleared; this runtime's orphan next trees cleared; unused `.next-isolated-*` removed;
 *   FRONTEND_DEV_PAUSED stamp (8h default, dev namespaces only)
 *
 * [POS]
 * Manual frontend resource reclaim for the shared dev stack. Only processes carrying this runtime's
 * dev stamp are signalled: the user's `myrm start` stack, the desktop client and other runtimes'
 * isolated stacks (reclaimed by their own reaper) are left alone.
 */
import { execSync, spawnSync } from 'child_process';
import { basename, dirname, join, resolve } from 'path';
import { readdirSync, rmSync, statSync, truncateSync } from 'fs';
import {
  ancestorHasFrontendMarker,
  filterOwnedPids,
  FRONTEND_MARKER,
  readCommand,
} from './cleanup-targets';
import { resolveCleanupPort } from './cleanup-port';
import { clearDevLock, clearStaleDevLock, isDistDirInUse } from './dev-lock';
import { listPidsOnPort } from './port-cleanup';

const ROOT = join(import.meta.dir, '..');
const DEFAULT_PAUSE_SEC = '28800';
const CLEANUP_PORT = resolveCleanupPort();

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

console.log(
  `🧹 Cleaning up myrm-agent-frontend next-server (shared dev UI :${CLEANUP_PORT} + own orphans)...\n`,
);

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

function signalPid(pid: string, label: string): boolean {
  console.log(`🔪 Killing ${label} PID ${pid}`);
  try {
    execSync(`kill -TERM ${pid}`);
    return true;
  } catch {
    try {
      execSync(`kill -9 ${pid}`);
      return true;
    } catch {
      return false;
    }
  }
}

/** SIGKILL the listeners on `port` that this runtime's stack started; any other holder keeps running. */
function killOwnedListeners(port: number): number {
  let killed = 0;
  for (const pid of filterOwnedPids(listPidsOnPort(port))) {
    console.log(`🔪 Killing listener PID ${pid} on port ${port}`);
    try {
      execSync(`kill -9 ${pid}`);
      killed += 1;
    } catch {
      // already gone
    }
  }
  return killed;
}

/** Kill this runtime's next-server / next / scripts/dev.ts trees of this frontend (any port). */
function killOrphanFrontendNextTrees(): number {
  let killed = 0;
  const pids = new Set<string>();

  const patterns = [
    `${FRONTEND_MARKER}/scripts/dev\\.ts`,
    `${FRONTEND_MARKER}/node_modules/\\.bin/next`,
    `${FRONTEND_MARKER}.*next dev`,
  ];
  for (const pattern of patterns) {
    try {
      const out = execSync(`pgrep -f '${pattern}' || true`, { encoding: 'utf-8' }).trim();
      for (const pid of out.split('\n').filter(Boolean)) {
        pids.add(pid);
      }
    } catch {
      // empty
    }
  }

  try {
    const out = execSync("pgrep -f 'next-server \\(v' || true", { encoding: 'utf-8' }).trim();
    for (const pid of out.split('\n').filter(Boolean)) {
      if (ancestorHasFrontendMarker(pid)) {
        pids.add(pid);
      }
    }
  } catch {
    // empty
  }

  const owned = new Set(filterOwnedPids([...pids]));
  for (const pid of pids) {
    if (!owned.has(pid)) {
      continue;
    }
    const cmd = readCommand(pid);
    if (!cmd) {
      continue;
    }
    if (!cmd.includes(FRONTEND_MARKER) && !ancestorHasFrontendMarker(pid)) {
      continue;
    }
    if (signalPid(pid, cmd.slice(0, 100))) {
      killed += 1;
    }
  }
  return killed;
}

showPortProcesses(CLEANUP_PORT);
let cleanedCount = killOwnedListeners(CLEANUP_PORT);
cleanedCount += killOrphanFrontendNextTrees();

try {
  execSync('sleep 0.4');
} catch {
  // ignore
}
cleanedCount += killOwnedListeners(CLEANUP_PORT);
cleanedCount += killOrphanFrontendNextTrees();

console.log('📊 Current memory usage:');
try {
  console.log(execSync('vm_stat | head -5', { encoding: 'utf-8' }));
} catch {
  // ignore
}

console.log(`\n✨ Cleanup complete! Terminated ${cleanedCount} process(es) of this runtime.`);
console.log('ℹ️  Other ports (e.g. myrm-website :3002) are untouched.');

function cleanIsolatedNextDirs(): number {
  const activeName = resolveActiveIsolatedDirName();
  let removed = 0;
  for (const entry of readdirSync(ROOT)) {
    if (!entry.startsWith('.next-isolated-')) {
      continue;
    }
    if (activeName && entry === activeName) {
      continue;
    }
    const target = join(ROOT, entry);
    // A dist dir with a live dev-server lock backs a running stack (the user's `myrm start`, or another runtime).
    if (isDistDirInUse(target)) {
      continue;
    }
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

function stripIsolatedTsconfig(): void {
  const result = spawnSync('python3', ['scripts/strip_isolated_tsconfig.py'], {
    cwd: ROOT,
    encoding: 'utf-8',
    stdio: 'inherit',
  });
  if (result.status !== 0) {
    console.warn('⚠️  strip_isolated_tsconfig.py exited with non-zero status');
  }
}

stripIsolatedTsconfig();

function writeFrontendDevPause(): void {
  const pauseSec = process.env.MYRM_FRONTEND_DEV_PAUSE_SEC?.trim() || DEFAULT_PAUSE_SEC;
  const pauseScript = join(
    import.meta.dir,
    '..',
    '..',
    'scripts',
    'dev',
    'lib',
    'e2e_core',
    'frontend_dev_pause.py',
  );
  const result = spawnSync(
    'python3',
    [pauseScript, 'write', '--seconds', pauseSec, '--reason', 'cleanup'],
    {
      encoding: 'utf-8',
      stdio: 'inherit',
    },
  );
  if (result.status !== 0) {
    console.error('❌ Failed to write frontend dev pause stamp — Agent may respawn next dev.');
    process.exit(result.status ?? 1);
  }
}

writeFrontendDevPause();
