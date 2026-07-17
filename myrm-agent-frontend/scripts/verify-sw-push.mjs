#!/usr/bin/env node
/** Fail CI when public/sw.js is missing Web Push handlers compiled from src/app/sw.ts. */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const swPath = resolve(import.meta.dirname, '../public/sw.js');
let contents = '';
try {
  contents = readFileSync(swPath, 'utf8');
} catch {
  console.error('ERROR: public/sw.js not found. Run next build + serwist inject-manifest.');
  process.exit(1);
}

const required = [
  'showNotification',
  'notificationclick',
  'favicon-32.png',
  'sanitizePushTargetUrl',
  'RESERVED_APP_SEGMENTS',
  'SETTINGS_PATH_PREFIX',
];
const missing = required.filter((token) => !contents.includes(token));
if (missing.length > 0) {
  console.error('ERROR: public/sw.js missing Web Push SW artifacts:', missing.join(', '));
  process.exit(1);
}

console.log('OK (public/sw.js includes Web Push handlers).');
