import { describe, it, expect } from 'vitest';
import { NextRequest } from 'next/server';
import { middleware } from '@/middleware';
import { NEXT_LOCALE_COOKIE_NAME } from '@/lib/utils/localeUtils';

describe('middleware marketing locale relay', () => {
  it('sets NEXT_LOCALE cookie and redirects without locale param', () => {
    const request = new NextRequest(
      'https://app.myrmagent.ai/auth/login?locale=en&redirect=%2Fpricing&utm_source=website',
    );
    const response = middleware(request);

    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe(
      'https://app.myrmagent.ai/auth/login?redirect=%2Fpricing&utm_source=website',
    );
    expect(response.cookies.get(NEXT_LOCALE_COOKIE_NAME)?.value).toBe('en');
  });

  it('relays locale on pricing entry path', () => {
    const request = new NextRequest('https://app.myrmagent.ai/pricing?locale=zh');
    const response = middleware(request);

    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe('https://app.myrmagent.ai/pricing');
    expect(response.cookies.get(NEXT_LOCALE_COOKIE_NAME)?.value).toBe('zh');
  });

  it('ignores invalid locale and continues the chain', () => {
    const request = new NextRequest('https://app.myrmagent.ai/auth/login?locale=fr');
    const response = middleware(request);

    expect(response.status).toBe(200);
    expect(response.headers.get('location')).toBeNull();
  });
});
