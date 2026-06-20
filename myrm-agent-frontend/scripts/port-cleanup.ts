/**
 * Kill only processes listening on a specific dev port (avoids killing other Next apps e.g. myrm-website :3002).
 */
import { execSync } from 'child_process';

export const APP_DEV_PORT = 3000;

export function listPidsOnPort(port: number): string[] {
  try {
    const pids = execSync(`lsof -ti :${port}`, { encoding: 'utf-8' }).trim();
    if (!pids) return [];
    return pids.split('\n').filter(Boolean);
  } catch {
    return [];
  }
}

/** Terminate listeners on `port`. Returns number of PIDs signalled. */
export function killListenersOnPort(port: number, force = false): number {
  const pidList = listPidsOnPort(port);
  if (pidList.length === 0) return 0;

  const cmd = force ? `kill -9 ${pidList.join(' ')}` : `kill ${pidList.join(' ')}`;
  console.log(
    `🔪 Killing process(es) on port ${port}${force ? ' (force)' : ''}: ${pidList.join(', ')}`,
  );
  try {
    execSync(cmd);
  } catch {
    if (!force) {
      return killListenersOnPort(port, true);
    }
    console.warn(`⚠️  Could not terminate all listeners on port ${port}: ${pidList.join(', ')}`);
    return 0;
  }
  if (!force) {
    try {
      execSync('sleep 0.3');
      const remaining = listPidsOnPort(port);
      if (remaining.length > 0) {
        execSync(`kill -9 ${remaining.join(' ')}`);
      }
    } catch {
      // already gone
    }
  }
  return pidList.length;
}
