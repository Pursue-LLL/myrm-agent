import { readFileSync } from 'node:fs';
import path from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { GET } from '../e2e-runtime-bootstrap.js/route';

const SCRIPT_PATH = path.join(process.cwd(), 'src/components/dev/e2e-runtime-bootstrap.js');

describe('GET /e2e-runtime-bootstrap.js', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it.each(['development', 'test'])('serves the bootstrap script verbatim and uncached in a %s build', async (env) => {
    vi.stubEnv('NODE_ENV', env);

    const response = await GET();

    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toBe('text/javascript; charset=utf-8');
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(await response.text()).toBe(readFileSync(SCRIPT_PATH, 'utf-8'));
  });

  it('answers 404 without any script body in a production build', async () => {
    vi.stubEnv('NODE_ENV', 'production');

    const response = await GET();

    expect(response.status).toBe(404);
    expect(await response.text()).not.toContain('__MYRM_E2E_RUNTIME__');
  });
});
