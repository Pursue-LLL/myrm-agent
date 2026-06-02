import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { AUTH_SESSION_COOKIE } from '@/lib/auth-cookie';
import { isSaasPublicPath } from '@/lib/marketing-paths';

function isSandboxDeployMode(): boolean {
  return process.env.NEXT_PUBLIC_DEPLOY_MODE === 'sandbox';
}

export function middleware(request: NextRequest) {
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
