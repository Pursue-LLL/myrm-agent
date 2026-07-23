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

describe('middleware Accept-Language auto-detection', () => {
  it('sets NEXT_LOCALE cookie from Accept-Language on first visit', () => {
    const request = new NextRequest('https://app.myrmagent.ai/', {
      headers: { 'accept-language': 'ja-JP,ja;q=0.9,en;q=0.8' },
    });
    const response = middleware(request);

    expect(response.status).toBe(200);
    expect(response.cookies.get(NEXT_LOCALE_COOKIE_NAME)?.value).toBe('ja');
  });

  it('falls back to en when no supported language matches', () => {
    const request = new NextRequest('https://app.myrmagent.ai/', {
      headers: { 'accept-language': 'fr-FR,fr;q=0.9,pt;q=0.8' },
    });
    const response = middleware(request);

    expect(response.status).toBe(200);
    expect(response.cookies.get(NEXT_LOCALE_COOKIE_NAME)?.value).toBe('en');
  });

  it('does not override existing NEXT_LOCALE cookie', () => {
    const request = new NextRequest('https://app.myrmagent.ai/', {
      headers: { 'accept-language': 'ja-JP,ja;q=0.9' },
    });
    request.cookies.set(NEXT_LOCALE_COOKIE_NAME, 'zh');
    const response = middleware(request);

    expect(response.status).toBe(200);
    expect(response.cookies.get(NEXT_LOCALE_COOKIE_NAME)).toBeUndefined();
  });

  it('auto-detects locale and preserves /workspace redirect', () => {
    const request = new NextRequest('https://app.myrmagent.ai/workspace', {
      headers: { 'accept-language': 'ko-KR,ko;q=0.9' },
    });
    const response = middleware(request);

    expect(response.status).toBe(301);
    expect(response.headers.get('location')).toContain('/work');
    expect(response.cookies.get(NEXT_LOCALE_COOKIE_NAME)?.value).toBe('ko');
  });

  it('detects zh-TW correctly', () => {
    const request = new NextRequest('https://app.myrmagent.ai/', {
      headers: { 'accept-language': 'zh-TW,zh;q=0.9,en;q=0.8' },
    });
    const response = middleware(request);

    expect(response.cookies.get(NEXT_LOCALE_COOKIE_NAME)?.value).toBe('zh-TW');
  });
});
