/**
 * [INPUT]
 * - locales/{lang}.json (POS: translation SSOT)
 *
 * [OUTPUT]
 * - computeLocaleContentVersion: short content hash of every locale file
 *
 * [POS]
 * Build-time cache key for /api/i18n/deferred. next.config.ts exposes it as NEXT_PUBLIC_LOCALE_VERSION so
 * the browser's long-lived cache entry changes exactly when a translation changes (upgrade), not on a timer.
 */
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

const VERSION_LENGTH = 12;

export function computeLocaleContentVersion(localesDir: string): string {
  const hash = createHash('sha1');
  // Sorted so the digest does not depend on directory enumeration order.
  const files = readdirSync(localesDir)
    .filter((name) => name.endsWith('.json'))
    .sort();

  for (const name of files) {
    hash.update(name);
    hash.update(readFileSync(path.join(localesDir, name)));
  }

  return hash.digest('hex').slice(0, VERSION_LENGTH);
}
