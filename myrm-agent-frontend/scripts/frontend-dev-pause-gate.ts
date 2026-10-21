/**
 * [INPUT]
 * - frontend_dev_pause.py check (POS: shared pause stamp SSOT)
 *
 * [OUTPUT]
 * - probeFrontendDevPause / enforceFrontendDevNotPaused / reclaimPausedDevListeners
 *
 * [POS]
 * TypeScript pause gate SSOT. Used by dev.ts and next.config.ts; reclaims LISTEN on late bunx exit.
 */
import { execSync, spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';

export type FrontendDevPauseProbe = 'active' | 'paused' | 'missing_script' | 'check_failed';

const PAUSE_LIFT_HINT =
  'Lift pause: bash myrm-agent/scripts/dev/dev-stack.sh frontend-only clear-pause';

function resolveDevPortFromArgv(): number {
  const argv = process.argv;
  const portFlagIdx = argv.findIndex((arg) => arg === '-p' || arg === '--port');
  if (portFlagIdx >= 0) {
    const parsed = Number.parseInt(argv[portFlagIdx + 1] ?? '', 10);
    if (Number.isInteger(parsed) && parsed > 0 && parsed <= 65535) {
      return parsed;
    }
  }
  const fromEnv = Number.parseInt(
    process.env.MYRM_FRONTEND_PORT ?? process.env.PORT ?? '3000',
    10,
  );
  return Number.isInteger(fromEnv) && fromEnv > 0 && fromEnv <= 65535 ? fromEnv : 3000;
}

/** Reclaim LISTEN sockets when next.config gate exits after Next already bound (bunx path). */
export function reclaimPausedDevListeners(): void {
  const port = resolveDevPortFromArgv();
  try {
    const pids = execSync(`lsof -iTCP:${port} -sTCP:LISTEN -t`, { encoding: 'utf-8' }).trim();
    if (!pids) {
      return;
    }
    for (const pid of pids.split('\n').filter(Boolean)) {
      try {
        execSync(`kill -TERM ${pid}`);
      } catch {
        try {
          execSync(`kill -9 ${pid}`);
        } catch {
          // ignore single pid
        }
      }
    }
  } catch {
    // port already free
  }
}

export function resolvePauseScriptPath(): string {
  // Check monorepo root scripts/dev/lib/e2e_core/frontend_dev_pause.py or fallback
  const candidates = [
    path.join(__dirname, '..', '..', '..', 'scripts', 'dev', 'lib', 'e2e_core', 'frontend_dev_pause.py'),
    path.join(__dirname, '..', '..', 'scripts', 'dev', 'lib', 'e2e_core', 'frontend_dev_pause.py'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return candidates[0];
}

export function probeFrontendDevPause(): FrontendDevPauseProbe {
  const pauseScript = resolvePauseScriptPath();
  if (!fs.existsSync(pauseScript)) {
    return 'active';
  }
  const result = spawnSync('python3', [pauseScript, 'check'], {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (result.error !== undefined || result.status === null) {
    return 'active';
  }
  return result.status === 0 ? 'paused' : 'active';
}

export function isFrontendDevPaused(): boolean {
  return probeFrontendDevPause() === 'paused';
}

export function enforceFrontendDevNotPaused(options?: {
  context?: string;
  exitCode?: number;
}): void {
  const context = options?.context ?? 'frontend dev';
  const exitCode = options?.exitCode ?? 1;
  const probe = probeFrontendDevPause();

  if (probe === 'missing_script') {
    console.error(
      `❌ Frontend dev pause gate: missing ${resolvePauseScriptPath()} — refusing ${context} (fail-closed).`,
    );
    process.exit(exitCode);
  }
  if (probe === 'check_failed') {
    console.error(`❌ Frontend dev pause gate: python3 check failed — refusing ${context} (fail-closed).`);
    process.exit(exitCode);
  }
  if (probe === 'paused') {
    console.error(`⏸️  Frontend dev paused (bun run cleanup). Refusing ${context}.`);
    console.error(`   ${PAUSE_LIFT_HINT}`);
    reclaimPausedDevListeners();
    process.exit(exitCode);
  }
}
