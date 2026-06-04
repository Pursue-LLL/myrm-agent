/**
 * Writes frontend SSE type manifest for server architecture tests.
 * Run: bun run scripts/export-known-sse-event-types.ts
 */
import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { KNOWN_SSE_EVENT_TYPE_VALUES } from '../src/store/chat/knownSseEventTypes';

const outPath = resolve(
  import.meta.dir,
  '../../myrm-agent-server/tests/fixtures/frontend_sse_event_types.json',
);

writeFileSync(
  outPath,
  `${JSON.stringify(KNOWN_SSE_EVENT_TYPE_VALUES, null, 2)}\n`,
  'utf8',
);
console.info(`Wrote ${KNOWN_SSE_EVENT_TYPE_VALUES.length} types to ${outPath}`);
