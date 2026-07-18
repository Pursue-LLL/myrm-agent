import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const SW_SOURCE = resolve(import.meta.dirname, '../../../app/sw.ts');

describe('sw.ts push handler wiring', () => {
  it('imports shared pushTargetUrl helpers and navigates on query mismatch', () => {
    const source = readFileSync(SW_SOURCE, 'utf8');
    expect(source).toContain("from '../lib/web-push/pushTargetUrl'");
    expect(source).toContain('resolvePushClientFocusAction');
    expect(source).toContain('client.navigate(targetUrl)');
  });
});
