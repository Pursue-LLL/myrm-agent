/**
 * [INPUT]
 * - lib/utils/localeUtils.ts (POS: App locale 解析与营销接力工具)
 * - lib/auth-cookie.ts (POS: SaaS sandbox 会话 cookie)
 * - lib/marketing-paths.ts (POS: SaaS 公开路径白名单)
 *
 * [OUTPUT]
 * - middleware(): 营销 `?locale=` 接力 + sandbox 未登录重定向
 *
 * [POS]
 * Next.js 边缘中间件：全 deploy mode 下首请求写入 NEXT_LOCALE；sandbox 模式追加鉴权重定向。
 */
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { AUTH_SESSION_COOKIE } from '@/lib/auth-cookie';
import { isSaasPublicPath } from '@/lib/marketing-paths';
import {
  NEXT_LOCALE_COOKIE_NAME,
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

  if (!isSandboxDeployMode()) {
    return NextResponse.next();
  }

  const { pathname } = request.nextUrl;

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
    return NextResponse.next();
  }

  const hasSession = request.cookies.get(AUTH_SESSION_COOKIE)?.value === '1';
  if (!hasSession) {
    const loginUrl = new URL('/auth/login', request.url);
    const returnPath = pathname + request.nextUrl.search;
    if (returnPath !== '/') {
      loginUrl.searchParams.set('redirect', returnPath);
    }
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
};
