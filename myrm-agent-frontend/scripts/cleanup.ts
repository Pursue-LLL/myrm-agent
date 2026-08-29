/**
 * [INPUT]
 * - port-cleanup::APP_DEV_PORT / killListenersOnPort (POS: shared :3000)
 * - frontend_dev_pause.py write (POS: shared pause stamp, 8h default)
 *
 * [OUTPUT]
 * - Shared :3000 cleared; orphan/isolated next for this frontend cleared
 * - FRONTEND_DEV_PAUSED stamp so Agent ensure cannot respawn for 8h
 *
 * [POS]
 * Manual frontend resource reclaim. Isolated E2E runtimes allocate UI ports in
 * 13000–14000 — cleanup discovers them via process cmdline (not 1001× lsof).
 */
import { execSync, spawnSync } from 'child_process';
import { basename, dirname, join, resolve } from 'path';
import { readdirSync, rmSync, statSync, truncateSync } from 'fs';
import { clearDevLock, clearStaleDevLock } from './dev-lock';
import { APP_DEV_PORT, killListenersOnPort, listPidsOnPort } from './port-cleanup';

const ROOT = join(import.meta.dir, '..');
const DEFAULT_PAUSE_SEC = '28800';
const FRONTEND_MARKER = 'myrm-agent-frontend';

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
  `🧹 Cleaning up myrm-agent-frontend next-server (shared :${APP_DEV_PORT} + isolated orphans)...\n`,
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

function readCommand(pid: string): string {
  try {
    return execSync(`ps -p ${pid} -o command=`, { encoding: 'utf-8' }).trim();
  } catch {
    return '';
  }
}

function readParentPid(pid: string): string | null {
  try {
    const ppid = execSync(`ps -p ${pid} -o ppid=`, { encoding: 'utf-8' }).trim();
    return /^\d+$/.test(ppid) ? ppid : null;
  } catch {
    return null;
  }
}

function ancestorHasFrontendMarker(pid: string, maxDepth = 6): boolean {
  let current: string | null = pid;
  for (let depth = 0; depth < maxDepth && current; depth += 1) {
    if (readCommand(current).includes(FRONTEND_MARKER)) {
      return true;
    }
    current = readParentPid(current);
  }
  return false;
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

/** Kill next-server / next / scripts/dev.ts belonging to this frontend (any port). */
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

  for (const pid of pids) {
    const cmd = readCommand(pid);
    if (!cmd) continue;
    if (!cmd.includes(FRONTEND_MARKER) && !ancestorHasFrontendMarker(pid)) {
      continue;
    }
    if (signalPid(pid, cmd.slice(0, 100))) {
      killed += 1;
    }
  }
  return killed;
}

showPortProcesses(APP_DEV_PORT);
let cleanedCount = killListenersOnPort(APP_DEV_PORT, true);
cleanedCount += killOrphanFrontendNextTrees();

try {
  execSync('sleep 0.4');
} catch {
  // ignore
}
cleanedCount += killListenersOnPort(APP_DEV_PORT, true);
cleanedCount += killOrphanFrontendNextTrees();

console.log('📊 Current memory usage:');
try {
  console.log(execSync('vm_stat | head -5', { encoding: 'utf-8' }));
} catch {
  // ignore
}

console.log(`\n✨ Cleanup complete! Terminated ${cleanedCount} process(es) (shared + isolated).`);
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
    console.warn('⚠️  Could not write frontend dev pause stamp (Agent may respawn next dev)');
  }
}

writeFrontendDevPause();
