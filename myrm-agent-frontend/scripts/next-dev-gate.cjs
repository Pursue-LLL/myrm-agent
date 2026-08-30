'use strict';
/**
 * Node --require preload: runs before Next.js loads (dev.ts spawn path).
 * SSOT remains frontend_dev_pause.py; this is an early fail-closed gate.
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
