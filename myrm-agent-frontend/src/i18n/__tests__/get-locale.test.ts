import { beforeEach, describe, expect, it, vi } from 'vitest';

const cookieValue = vi.hoisted(() => ({ current: undefined as string | undefined }));

vi.mock('next/headers', () => ({
  cookies: async () => ({
    get: (name: string) => (name === 'NEXT_LOCALE' && cookieValue.current ? { value: cookieValue.current } : undefined),
  }),
}));

import { getLocale } from '../index';

describe('getLocale', () => {
  beforeEach(() => {
    cookieValue.current = undefined;
  });

  it('returns a supported locale from the cookie', async () => {
    cookieValue.current = 'ja';
    expect(await getLocale()).toBe('ja');
  });

  it('falls back to the default locale when the cookie holds an unsupported value', async () => {
    cookieValue.current = 'zh-CN';
    expect(await getLocale()).toBe('zh');
  });

  it('falls back to the default locale without a cookie', async () => {
    expect(await getLocale()).toBe('zh');
  });
});
