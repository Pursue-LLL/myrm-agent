/**
 * [INPUT]
 * - frontend_dev_pause.py check (POS: shared pause stamp SSOT)
 *
 * [OUTPUT]
 * - probeFrontendDevPause / enforceFrontendDevNotPaused
 *
 * [POS]
 * TypeScript SSOT for frontend dev pause gate. Used by dev.ts and next.config.ts
 * so direct `bunx next dev` cannot bypass cleanup pause.
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';

export type FrontendDevPauseProbe = 'active' | 'paused' | 'missing_script' | 'check_failed';

const PAUSE_LIFT_HINT =
  'Lift pause: bash myrm-agent/scripts/dev/dev-stack.sh frontend-only clear-pause';

export function resolvePauseScriptPath(): string {
  return path.join(__dirname, '..', '..', 'scripts', 'dev', 'lib', 'e2e_core', 'frontend_dev_pause.py');
}

export function probeFrontendDevPause(): FrontendDevPauseProbe {
  const pauseScript = resolvePauseScriptPath();
  if (!fs.existsSync(pauseScript)) {
    return 'missing_script';
  }
  const result = spawnSync('python3', [pauseScript, 'check'], {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (result.error !== undefined || result.status === null) {
    return 'check_failed';
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
    process.exit(exitCode);
  }
}
