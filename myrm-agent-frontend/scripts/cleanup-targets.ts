/**
 * [INPUT]
 * - dev_ownership.py filter / partition (POS: positive proof that a process was started by the runtime about to signal it)
 *
 * [OUTPUT]
 * - filterOwnedPids: the subset of pids stamped by the given runtime (fails closed)
 * - filterReclaimablePids: the listeners `bun run dev` may reclaim on its own port (fails closed)
 * - readCommand / readParentPid / FRONTEND_MARKER: process-tree primitives shared with `bun run cleanup`
 *
 * [POS]
 * Decides what `bun run cleanup` and `bun run dev` may touch: processes this runtime's dev
 * stack started, and un-stamped leftovers of this frontend's own `next dev` — never the user's
 * `myrm start` stack, the desktop client or another runtime. Self-contained on purpose: the pause
 * gate that `next.config.ts` loads reaches it, so it may import nothing outside this directory.
 */
import { execFileSync, spawnSync } from 'child_process';
import path from 'path';

const DEV_OWNERSHIP_PY = path.join(
  __dirname,
  '..',
  '..',
  'scripts',
  'dev',
  'lib',
  'e2e_core',
  'dev_ownership.py',
);

export const FRONTEND_MARKER = 'myrm-agent-frontend';
/**
 * The `next dev` this frontend starts, or the `scripts/dev.ts` supervisor in front of it: a node or
 * bun process running those files. A shell whose command line merely mentions them is not one.
 */
const FRONTEND_DEV_COMMAND = new RegExp(
  `^(?:\\S*/)?(?:node|bun)\\s.*${FRONTEND_MARKER}/(?:node_modules/(?:\\.bin|next/dist/bin)/next dev\\b|scripts/dev\\.ts)`,
);
const MAX_ANCESTOR_DEPTH = 6;

export type PidVerdict = 'owned' | 'unstamped' | 'foreign' | 'unknown';

export function currentRuntimeId(): string {
  return process.env.MYRM_RUNTIME_NAMESPACE?.trim() || 'shared';
}

function psField(pid: string, field: 'command' | 'ppid'): string {
  try {
    return execFileSync('ps', ['-p', pid, '-o', `${field}=`], {
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return '';
  }
}

export function readCommand(pid: string): string {
  return psField(pid, 'command');
}

export function readParentPid(pid: string): string | null {
  const ppid = psField(pid, 'ppid');
  return /^\d+$/.test(ppid) ? ppid : null;
}

/** Commands of `pid` and its ancestors, nearest first. */
function processChainCommands(pid: string): string[] {
  const commands: string[] = [];
  let current: string | null = pid;
  for (let depth = 0; depth < MAX_ANCESTOR_DEPTH && current; depth += 1) {
    commands.push(readCommand(current));
    current = readParentPid(current);
  }
  return commands;
}

export function ancestorHasFrontendMarker(pid: string): boolean {
  return processChainCommands(pid).some((command) => command.includes(FRONTEND_MARKER));
}

/** A `next dev` of this frontend (or a child of one): what an earlier bare `bun run dev` leaves behind. */
function isFrontendDevProcess(pid: string): boolean {
  return processChainCommands(pid).some(
    (command) => FRONTEND_DEV_COMMAND.test(command),
  );
}

function runOwnership(subcommand: 'filter' | 'partition', runtimeId: string, pids: readonly string[]) {
  const result = spawnSync(
    'python3',
    [DEV_OWNERSHIP_PY, subcommand, '--runtime-id', runtimeId, ...pids],
    { encoding: 'utf-8' },
  );
  if (result.status !== 0) {
    const reason = result.error?.message ?? `exit ${result.status}`;
    console.warn(`⚠️  Ownership check failed (${reason}); leaving ${pids.length} process(es) untouched.`);
    return null;
  }
  return result;
}

/** Ownership is the dev stamp in the process environment, never the command line or the port. */
export function filterOwnedPids(
  pids: readonly string[],
  runtimeId: string = currentRuntimeId(),
): string[] {
  if (pids.length === 0) {
    return [];
  }
  const result = runOwnership('filter', runtimeId, pids);
  if (!result) {
    return [];
  }
  if (result.stderr) {
    process.stderr.write(result.stderr);
  }
  return result.stdout
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function partitionPids(pids: readonly string[], runtimeId: string): Map<string, PidVerdict> {
  const verdicts = new Map<string, PidVerdict>();
  const result = runOwnership('partition', runtimeId, pids);
  for (const line of result?.stdout.split('\n') ?? []) {
    const [pid, verdict] = line.trim().split(' ');
    if (pid && verdict) {
      verdicts.set(pid, verdict as PidVerdict);
    }
  }
  return verdicts;
}

/**
 * The listeners `bun run dev` may signal on its own port: this runtime's stamped processes and
 * un-stamped `next dev` leftovers of this frontend. A process stamped by another runtime (the
 * `user` stack), the desktop client or any unrelated program holding the port is left alone.
 */
export function filterReclaimablePids(
  pids: readonly string[],
  runtimeId: string = currentRuntimeId(),
): string[] {
  if (pids.length === 0) {
    return [];
  }
  const verdicts = partitionPids(pids, runtimeId);
  return pids.filter((pid) => {
    const verdict = verdicts.get(pid);
    return verdict === 'owned' || (verdict === 'unstamped' && isFrontendDevProcess(pid));
  });
}
