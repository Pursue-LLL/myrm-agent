/**
 * [INPUT]
 * - dev-ports.mjs::sharedFrontendPort (POS: Default ports of the user, shared dev and isolated stacks — SSOT)
 * - dev_ownership.py filter (POS: positive proof that a process was started by the runtime about to signal it)
 *
 * [OUTPUT]
 * - resolveCleanupPort: the UI port `bun run cleanup` reclaims
 * - filterOwnedPids: the subset of pids stamped by the given runtime (fails closed)
 *
 * [POS]
 * Decides what `bun run cleanup` may touch: the shared dev UI and processes this runtime's dev
 * stack started — never the user's `myrm start` stack, the desktop client or another runtime.
 */
import { spawnSync } from 'child_process';
import path from 'path';

import { sharedFrontendPort } from '../../scripts/dev/lib/dev-ports.mjs';

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

/** An explicit `MYRM_FRONTEND_PORT` wins; otherwise the shared dev UI (3000 is the user's stack). */
export function resolveCleanupPort(): number {
  const explicit = Number.parseInt(process.env.MYRM_FRONTEND_PORT ?? '', 10);
  return Number.isInteger(explicit) && explicit > 0 && explicit <= 65535
    ? explicit
    : sharedFrontendPort();
}

export function currentRuntimeId(): string {
  return process.env.MYRM_RUNTIME_NAMESPACE?.trim() || 'shared';
}

/** Ownership is the dev stamp in the process environment, never the command line or the port. */
export function filterOwnedPids(
  pids: readonly string[],
  runtimeId: string = currentRuntimeId(),
): string[] {
  if (pids.length === 0) {
    return [];
  }
  const result = spawnSync(
    'python3',
    [DEV_OWNERSHIP_PY, 'filter', '--runtime-id', runtimeId, ...pids],
    { encoding: 'utf-8' },
  );
  if (result.status !== 0) {
    const reason = result.error?.message ?? `exit ${result.status}`;
    console.warn(`⚠️  Ownership check failed (${reason}); leaving ${pids.length} process(es) untouched.`);
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
