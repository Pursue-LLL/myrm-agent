import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { LONG_RUNNING_REQUEST_TIMEOUT_MS } from '../requestTimeouts';

describe('LONG_RUNNING_REQUEST_TIMEOUT_MS', () => {
  it('is wired into the Next rewrite proxy so API calls are not cut at its 30s default', () => {
    const nextConfig = readFileSync(path.resolve(__dirname, '../../../../next.config.ts'), 'utf8');

    expect(nextConfig).toContain("from './src/lib/constants/requestTimeouts'");
    expect(nextConfig).toMatch(/proxyTimeout:\s*LONG_RUNNING_REQUEST_TIMEOUT_MS/);
  });

  it('is a positive integer number of milliseconds', () => {
    expect(Number.isInteger(LONG_RUNNING_REQUEST_TIMEOUT_MS)).toBe(true);
    expect(LONG_RUNNING_REQUEST_TIMEOUT_MS).toBeGreaterThan(0);
  });
});
