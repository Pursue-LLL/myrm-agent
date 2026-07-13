#!/usr/bin/env bun
/**
 * Chrome MCP E2E model seed — stdout JSON { ok, seeded, providerId?, modelId? }
 */

import { seedChromeE2eProviders } from './chrome-e2e-seed-providers.mjs';

try {
  const result = await seedChromeE2eProviders();
  console.log(JSON.stringify({ ok: true, ...result }));
} catch (err) {
  const message = err instanceof Error ? err.message : String(err);
  console.error(`CHROME_E2E_MODEL_SEED_FAIL: ${message}`);
  process.exit(1);
}
