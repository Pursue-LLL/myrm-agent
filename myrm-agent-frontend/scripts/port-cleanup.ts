/**
 * [INPUT]
 * - child_process::execSync (POS: lsof/kill for LISTEN sockets)
 * - cleanup-targets::filterReclaimablePids (POS: which listeners this dev server may signal)
 *
 * [OUTPUT]
 * - listPidsOnPort: LISTEN PIDs on a port
 * - killListenersOnPort: terminate the reclaimable LISTEN holders (not Chrome ESTABLISHED clients)
 * - foreignListenersOnPort: LISTEN holders this dev server must leave running
 * - APP_DEV_PORT constant (MYRM_FRONTEND_PORT, default 3000)
 *
 * [POS]
 * Scoped port cleanup for the dev server's own port. A listener stamped by another runtime (the
 * user's `myrm start` stack on :3000) or started by an unrelated program is never signalled.
 */
import { execSync } from 'child_process';

import { filterReclaimablePids, readCommand } from './cleanup-targets';

function resolveDevPort(): number {
  const parsed = Number.parseInt(process.env.MYRM_FRONTEND_PORT ?? '3000', 10);
  return Number.isInteger(parsed) && parsed > 0 && parsed <= 65535 ? parsed : 3000;
}

export const APP_DEV_PORT = resolveDevPort();

/** PIDs with a TCP LISTEN socket on `port` (excludes Chrome clients on ESTABLISHED). */
export function listPidsOnPort(port: number): string[] {
  try {
    const pids = execSync(`lsof -iTCP:${port} -sTCP:LISTEN -t`, { encoding: 'utf-8' }).trim();
    if (!pids) {
      return [];
    }
    return [...new Set(pids.split('\n').filter(Boolean))];
  } catch {
    return [];
  }
}

/**
 * Live listeners on `port` that `killListenersOnPort` leaves running: not this dev server's to
 * reclaim. A listener that already exited (lsof can lag a just-killed process) is not one.
 */
export function foreignListenersOnPort(port: number): string[] {
  const listeners = listPidsOnPort(port);
  const reclaimable = new Set(filterReclaimablePids(listeners));
  return listeners.filter((pid) => !reclaimable.has(pid) && readCommand(pid) !== '');
}

/** Terminate the reclaimable listeners on `port`. Returns number of PIDs signalled. */
export function killListenersOnPort(port: number, force = false): number {
  const pidList = filterReclaimablePids(listPidsOnPort(port));
  if (pidList.length === 0) {
    return 0;
  }

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
      const remaining = filterReclaimablePids(listPidsOnPort(port));
      if (remaining.length > 0) {
        execSync(`kill -9 ${remaining.join(' ')}`);
      }
    } catch {
      // already gone
    }
  }
  return pidList.length;
}
