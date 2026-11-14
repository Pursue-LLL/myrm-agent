/**
 * [INPUT]
 * - `<frontend>/../myrm-agent-server/.venv/bin/python` and PATH: where an interpreter for `scripts/dev/lib` can be found
 *
 * [OUTPUT]
 * - resolveDevPython: first candidate that is executed and reports Python >= 3.11, else null
 * - ensureDevPython: that interpreter, or plain `python3` plus a startup warning when the machine has none
 *
 * [POS]
 * `scripts/dev/lib` (the memory guard's probe among it) uses StrEnum, so it needs Python >= 3.11. Which
 * interpreter a bare `python3` names depends on how PATH was built: macOS ships 3.9 at /usr/bin, and a
 * process that never sourced the user's profile (launchd, a sandboxed agent) sees only that one. Unchecked,
 * the probe then fails three samples in a row and the guard switches itself off 90 s after start, with
 * nothing said at launch. Each candidate is executed instead of trusted by name, in the order
 * `scripts/maintainer/sync_external_repos.sh` uses.
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const FLOOR = [3, 11] as const;
const PROBE_SOURCE = `import sys; sys.exit(sys.version_info < (${FLOOR.join(', ')}))`;
const PROBE_TIMEOUT_MS = 10_000;
const PATH_NAMES = ['python3.13', 'python3.12', 'python3.11', 'python3'];

export type ProbePython = (candidate: string) => boolean;

export interface ResolveOptions {
  frontendRoot: string;
  envPath: string | undefined;
  probe?: ProbePython;
  warn?: (message: string) => void;
}

export function probePython(candidate: string): boolean {
  const result = spawnSync(candidate, ['-c', PROBE_SOURCE], { stdio: 'ignore', timeout: PROBE_TIMEOUT_MS });
  return result.status === 0;
}

/** The server venv first (uv-managed), then each versioned name across PATH before the bare `python3`. */
function candidates({ frontendRoot, envPath }: ResolveOptions): string[] {
  const venv = path.join(frontendRoot, '..', 'myrm-agent-server', '.venv', 'bin', 'python');
  const dirs = (envPath ?? '').split(path.delimiter).filter(Boolean);
  const named = PATH_NAMES.flatMap((name) => dirs.map((dir) => path.join(dir, name)));
  return [...new Set([venv, ...named])].filter((file) => fs.existsSync(file));
}

export function resolveDevPython(options: ResolveOptions): string | null {
  return candidates(options).find(options.probe ?? probePython) ?? null;
}

export function ensureDevPython(options: ResolveOptions): string {
  const found = resolveDevPython(options);
  if (found !== null) {
    return found;
  }
  const floor = FLOOR.join('.');
  (options.warn ?? console.warn)(
    `FOOTPRINT_GUARD_OFF: no Python >= ${floor} (no server venv; ${PATH_NAMES.join(' / ')} are absent or older), ` +
      'so the Next.js memory guard cannot measure and will switch itself off. Run ./myrm setup or install Python 3.13.',
  );
  return 'python3';
}
