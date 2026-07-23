/**
 * [INPUT]
 * - lib/utils/localeUtils.ts (POS: Locale 工具集。供 middleware 自动检测、营销接力、客户端读取和后端格式归一化)
 * - lib/auth-cookie.ts (POS: SaaS sandbox 会话 cookie)
 * - lib/marketing-paths.ts (POS: SaaS 公开路径白名单)
 *
 * [OUTPUT]
 * - middleware(): 营销 `?locale=` 接力 + 首次 Accept-Language 自动检测 + sandbox 未登录重定向
 *
 * [POS]
 * Next.js 边缘中间件：首次访问自动检测 OS locale 写入 NEXT_LOCALE cookie；营销站 locale 参数接力；sandbox 模式鉴权重定向。
 */
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { AUTH_SESSION_COOKIE } from '@/lib/auth-cookie';
import { isSaasPublicPath } from '@/lib/marketing-paths';
import {
  NEXT_LOCALE_COOKIE_NAME,
  negotiateLocale,
  parseLocaleQueryParam,
  urlWithoutLocaleParam,
} from '@/lib/utils/localeUtils';

const LOCALE_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365;

function isSandboxDeployMode(): boolean {
  return process.env.NEXT_PUBLIC_DEPLOY_MODE === 'sandbox';
}

function relayMarketingLocale(request: NextRequest): NextResponse | null {
  const locale = parseLocaleQueryParam(request.nextUrl.searchParams.get('locale'));
  if (!locale) return null;

  const redirectUrl = urlWithoutLocaleParam(request.nextUrl);
  const response = NextResponse.redirect(redirectUrl);
  response.cookies.set(NEXT_LOCALE_COOKIE_NAME, locale, {
    path: '/',
    maxAge: LOCALE_COOKIE_MAX_AGE_SECONDS,
  });
  return response;
}

export function middleware(request: NextRequest) {
  const localeRelay = relayMarketingLocale(request);
  if (localeRelay) {
    return localeRelay;
  }

  const needsLocaleDetection = !request.cookies.has(NEXT_LOCALE_COOKIE_NAME);
  const { pathname } = request.nextUrl;

  if (pathname === '/workspace') {
    const url = request.nextUrl.clone();
    url.pathname = '/work';
    const response = NextResponse.redirect(url, 301);
    if (needsLocaleDetection) {
      attachDetectedLocale(request, response);
    }
    return response;
  }

  if (!isSandboxDeployMode()) {
    const response = NextResponse.next();
    if (needsLocaleDetection) {
      attachDetectedLocale(request, response);
    }
    return response;
  }

  if (
    pathname.startsWith('/api/') ||
    pathname.startsWith('/_next/') ||
    pathname.startsWith('/icons/') ||
    pathname === '/favicon.ico' ||
    pathname === '/sw.js' ||
    pathname === '/manifest.json'
  ) {
    return NextResponse.next();
  }

  if (isSaasPublicPath(pathname)) {
    const response = NextResponse.next();
    if (needsLocaleDetection) {
      attachDetectedLocale(request, response);
    }
    return response;
  }

  const hasSession = request.cookies.get(AUTH_SESSION_COOKIE)?.value === '1';
  if (!hasSession) {
    const loginUrl = new URL('/auth/login', request.url);
    const returnPath = pathname + request.nextUrl.search;
    if (returnPath !== '/') {
      loginUrl.searchParams.set('redirect', returnPath);
    }
    const response = NextResponse.redirect(loginUrl);
    if (needsLocaleDetection) {
      attachDetectedLocale(request, response);
    }
    return response;
  }

  const response = NextResponse.next();
  if (needsLocaleDetection) {
    attachDetectedLocale(request, response);
  }
  return response;
}

function attachDetectedLocale(request: NextRequest, response: NextResponse): void {
  const detected = negotiateLocale(request.headers.get('accept-language'));
  response.cookies.set(NEXT_LOCALE_COOKIE_NAME, detected, {
    path: '/',
    maxAge: LOCALE_COOKIE_MAX_AGE_SECONDS,
  });
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
};
