/**
 * [INPUT]
 * - child_process::execSync (POS: lsof/kill for LISTEN sockets)
 *
 * [OUTPUT]
 * - listPidsOnPort: LISTEN PIDs on a port
 * - killListenersOnPort: terminate LISTEN holders only (not Chrome ESTABLISHED clients)
 * - APP_DEV_PORT constant (3000)
 *
 * [POS]
 * Scoped port cleanup for myrm-agent-frontend dev (:3000). Avoids killing unrelated apps on other ports.
 */
import { execSync } from 'child_process';

function resolveDevPort(): number {
  const parsed = Number.parseInt(process.env.MYRM_FRONTEND_PORT ?? '3000', 10);
  return Number.isInteger(parsed) && parsed > 0 && parsed <= 65535 ? parsed : 3000;
}

export const APP_DEV_PORT = resolveDevPort();

/** PIDs with a TCP LISTEN socket on `port` (excludes Chrome clients on ESTABLISHED). */
export function listPidsOnPort(port: number): string[] {
  try {
    const pids = execSync(`lsof -iTCP:${port} -sTCP:LISTEN -t`, { encoding: 'utf-8' }).trim();
    if (!pids) return [];
    return [...new Set(pids.split('\n').filter(Boolean))];
  } catch {
    return [];
  }
}

/** Terminate listeners on `port`. Returns number of PIDs signalled. */
export function killListenersOnPort(port: number, force = false): number {
  const pidList = listPidsOnPort(port);
  if (pidList.length === 0) return 0;

  const cmd = force ? `kill -9 ${pidList.join(' ')}` : `kill ${pidList.join(' ')}`;
  console.log(`🔪 Killing process(es) on port ${port}${force ? ' (force)' : ''}: ${pidList.join(', ')}`);
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
