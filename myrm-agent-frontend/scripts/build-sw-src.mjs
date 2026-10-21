#!/usr/bin/env node
/** Bundle src/app/sw.ts for serwist inject-manifest (resolves lib imports). */

import { accessSync, constants, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import * as esbuild from 'esbuild';

const root = resolve(import.meta.dirname, '..');
const entry = resolve(root, 'src/app/sw.ts');
const outDir = resolve(root, '.serwist');
const outfile = resolve(outDir, 'sw-inject-src.js');

try {
  accessSync(entry, constants.R_OK);
} catch {
  console.error(`ERROR: Service worker entry not found: ${entry}`);
  console.error('Run from myrm-agent-frontend root after src/app/sw.ts exists.');
  process.exit(1);
}

mkdirSync(outDir, { recursive: true });

await esbuild.build({
  entryPoints: [entry],
  bundle: true,
  outfile,
  format: 'esm',
  platform: 'browser',
  target: 'es2022',
  logLevel: 'info',
});

console.log(`OK (bundled service worker → ${outfile}).`);
