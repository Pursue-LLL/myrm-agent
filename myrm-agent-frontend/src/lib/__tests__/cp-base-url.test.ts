import { afterEach, describe, expect, it } from 'vitest';
import { resolveCpBaseUrl } from '@/lib/cp-base-url';

describe('resolveCpBaseUrl', () => {
  const original = process.env.NEXT_PUBLIC_CP_BASE_URL;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.NEXT_PUBLIC_CP_BASE_URL;
    } else {
      process.env.NEXT_PUBLIC_CP_BASE_URL = original;
    }
  });

  it('uses configured URL without trailing slash', () => {
    process.env.NEXT_PUBLIC_CP_BASE_URL = 'http://localhost:8003/';
    expect(resolveCpBaseUrl()).toBe('http://localhost:8003');
  });

  it('falls back to localhost:8003 on server', () => {
    delete process.env.NEXT_PUBLIC_CP_BASE_URL;
    expect(resolveCpBaseUrl()).toBe('http://localhost:8003');
  });
});
