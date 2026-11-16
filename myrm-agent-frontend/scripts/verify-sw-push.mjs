#!/usr/bin/env node
/**
 * Fail the build when public/sw.js is not a production build of src/app/sw.ts: it must carry the
 * Web Push handlers and must not carry Serwist's development logger.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const swPath = resolve(import.meta.dirname, '../public/sw.js');
let contents = '';
try {
  contents = readFileSync(swPath, 'utf8');
} catch {
  console.error('ERROR: public/sw.js not found. Run next build + serwist build.');
  process.exit(1);
}

// Markers survive minification: property names and string literals are never renamed. The quoted
// "/settings/" comes only from the bundled pushTargetUrl module; unquoted, a prerendered settings
// page in the precache manifest (server/app/settings/....html) would satisfy it without that module.
const required = ['showNotification', 'notificationclick', 'favicon-32.png', '.navigate(', '"/settings/"'];
// A production build (NODE_ENV=production) folds the development logger away.
const forbidden = ['groupCollapsed'];

const missing = required.filter((token) => !contents.includes(token));
const present = forbidden.filter((token) => contents.includes(token));
if (missing.length > 0) {
  console.error('ERROR: public/sw.js missing Web Push SW artifacts:', missing.join(', '));
}
if (present.length > 0) {
  console.error('ERROR: public/sw.js is a development build (Serwist development logger present):', present.join(', '));
}
if (missing.length > 0 || present.length > 0) {
  process.exit(1);
}

console.log('OK (public/sw.js is a production build with Web Push handlers).');
