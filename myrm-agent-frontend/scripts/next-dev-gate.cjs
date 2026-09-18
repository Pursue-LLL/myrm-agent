'use strict';
/**
 * Node --require preload: runs before Next.js loads (dev.ts spawn path).
 *
 * Two responsibilities:
 * 1. Early fail-closed pause gate (SSOT remains frontend_dev_pause.py).
 * 2. Point next-env.d.ts at THIS lane's dist dir before Next writes it.
 *    Next rewrites next-env.d.ts unconditionally (no `extends` escape hatch, unlike
 *    tsconfig) using MYRM_NEXT_DIST_DIR. Without this, lane B reads lane A's stale
 *    `.next-isolated-<A>/dev/types` imports until B's own Next overwrites them, so a
 *    lane can inherit another lane's dead route-type paths.
 */
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const isDevArgv = process.argv.some((arg) => arg === 'dev' || arg.endsWith(`${path.sep}next`) && process.argv.includes('dev'));
if (process.env.NODE_ENV !== 'development' && !isDevArgv) {
  return;
}

const pauseScript = path.join(__dirname, '..', '..', 'scripts', 'dev', 'lib', 'e2e_core', 'frontend_dev_pause.py');
const liftHint = 'Lift pause: bash myrm-agent/scripts/dev/dev-stack.sh frontend-only clear-pause';

if (!fs.existsSync(pauseScript)) {
  console.error(`❌ Frontend dev pause gate: missing ${pauseScript} — refusing next dev (fail-closed).`);
  process.exit(1);
}

const result = spawnSync('python3', [pauseScript, 'check'], { encoding: 'utf8' });
if (result.error || result.status === null) {
  console.error('❌ Frontend dev pause gate: python3 check failed — refusing next dev (fail-closed).');
  process.exit(1);
}
if (result.status === 0) {
  console.error('⏸️  Frontend dev paused (bun run cleanup). Refusing next dev (preload gate).');
  console.error(`   ${liftHint}`);
  process.exit(1);
}

/**
 * Keep next-env.d.ts pointing at the dist dir this lane was started with.
 *
 * Next computes the import path from MYRM_NEXT_DIST_DIR, so pre-seeding the file with
 * the same value makes its own write a no-op (it compares content and skips). The
 * rewrite is idempotent and only touches lane-owned import lines: the reference types
 * and the "do not edit" notice are preserved verbatim.
 */
function alignNextEnvDistDir() {
  const frontendRoot = path.join(__dirname, '..');
  const nextEnvPath = path.join(frontendRoot, 'next-env.d.ts');
  const distDir = (process.env.MYRM_NEXT_DIST_DIR || '.next').replace(/\\/g, '/').replace(/\/+$/, '');
  // Next is handed `<dist>/dev` and emits `<dist>/dev/types/...`, so a flat `.next`
  // lane's imports become `.next/dev/types/...` (confirmed against the generated file).
  const typesBase = distDir.endsWith('/dev') ? distDir : `${distDir}/dev`;
  const desiredImports = [
    `import "./${typesBase}/types/routes.d.ts";`,
    `import "./${typesBase}/types/root-params.d.ts";`,
  ];

  let current = '';
  try {
    current = fs.readFileSync(nextEnvPath, 'utf8');
  } catch {
    return; // Absent file: Next will create it correctly for this lane.
  }

  const eol = current.includes('\r\n') ? '\r\n' : '\n';
  const lines = current.split(/\r?\n/);
  const importIdx = [];
  let lastReferenceIdx = -1;
  lines.forEach((line, index) => {
    if (line.startsWith('import "./')) importIdx.push(index);
    if (line.startsWith('/// <reference')) lastReferenceIdx = index;
  });

  const alreadyAligned =
    importIdx.length === desiredImports.length &&
    desiredImports.every((line) => lines.includes(line));
  if (alreadyAligned) {
    return;
  }

  // Replace in place so the result matches Next's canonical layout byte-for-byte;
  // that makes Next's own subsequent write a no-op instead of a second rewrite.
  const kept = lines.filter((_, index) => !importIdx.includes(index));
  const insertAt = importIdx.length > 0 ? importIdx[0] : lastReferenceIdx + 1;
  const aligned = [
    ...kept.slice(0, insertAt),
    ...desiredImports,
    ...kept.slice(insertAt),
  ].join(eol);
  fs.writeFileSync(nextEnvPath, aligned, 'utf8');
}

alignNextEnvDistDir();
