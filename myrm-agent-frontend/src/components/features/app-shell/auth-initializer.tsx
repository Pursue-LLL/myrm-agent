'use client';

/**
 * 认证状态初始化组件
 *
 * 在应用顶层挂载，自动处理：
 * 1. 初始化认证状态（按部署模式分发）
 * 2. 处理 OAuth 回调（Sandbox 模式）
 * 3. 全局 401 拦截：API 请求返回 401 时自动重定向到 /auth/login
 * 4. Tauri Remote 模式首次 setup 自动跳转
 *
 * 部署模式：
 * - 本地模式（Tauri/Local）：自动登录 local_user，无需 OAuth
 * - Sandbox 模式：必须 OAuth 登录
 */

import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import useAuthStore from '@/store/useAuthStore';
import AuthCallback from './auth-callback';
import { isTauriRuntime, isLocalMode, shouldRedirectToLoginOnAuthFailure } from '@/lib/deploy-mode';
import { clearAuthToken } from '@/lib/guest';

const AUTH_PATHS = [
  '/auth/login',
  '/auth/setup',
  '/auth/oauth/callback',
  '/auth/mcp-callback',
];

function isAuthPage(): boolean {
  if (typeof window === 'undefined') return false;
  return AUTH_PATHS.some((p) => window.location.pathname.startsWith(p));
}

/**
 * 安装全局 fetch 拦截器。
 * 检测 API 请求的 401 响应，自动重定向到 /auth/login。
 * 对本地模式（Tauri/Local 非 Remote）无副作用（后端不会返回 401）。
 */
function installFetchInterceptor(): () => void {
  const originalFetch = window.fetch;
  let redirecting = false;

  window.fetch = async function interceptedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const response = await originalFetch.call(window, input, init);

    if (
      shouldRedirectToLoginOnAuthFailure() &&
      response.status === 401 &&
      !redirecting &&
      !isAuthPage()
    ) {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/') && !url.includes('/api/proxy-models') && !url.includes('/api/models-dev')) {
        redirecting = true;
        clearAuthToken();
        window.location.href = '/auth/login';
      }
    }

    return response;
  };

  return () => {
    window.fetch = originalFetch;
  };
}

/**
 * In Tauri Remote mode, check if admin setup is needed.
 * If no admin exists, retrieve the setup token from Tauri and redirect.
 */
async function handleTauriRemoteSetup(): Promise<void> {
  if (!isTauriRuntime() || isAuthPage()) return;

  try {
    const { getWebuiUrl } = await import('@/lib/api');
    const res = await fetch(getWebuiUrl('/auth/status'), { credentials: 'include' });
    if (!res.ok) return;

    const status = await res.json();
    if (status.is_setup_done || status.is_authenticated) return;

    const { invoke } = await import('@tauri-apps/api/core');
    const token: string | null = await invoke('get_setup_token');
    if (token) {
      window.location.href = `/auth/setup?token=${encodeURIComponent(token)}`;
    }
  } catch {
    // Non-Tauri or backend not ready — silently ignore
  }
}

function isDedicatedAuthRoute(pathname: string | null): boolean {
  if (!pathname) return false;
  return (
    pathname.startsWith('/auth/oauth/callback')
    || pathname.startsWith('/auth/mcp-callback')
  );
}

export default function AuthInitializer() {
  const pathname = usePathname();
  const { isInitialized, initAuth, initTauriLocalUser } = useAuthStore();
  const localMode = isLocalMode();
  const interceptorInstalledRef = useRef(false);

  useEffect(() => {
    if (isInitialized) return;

    if (localMode) {
      initTauriLocalUser();
    } else {
      initAuth();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localMode, isInitialized]);

  useEffect(() => {
    if (interceptorInstalledRef.current) return;
    interceptorInstalledRef.current = true;

    const cleanup = installFetchInterceptor();

    handleTauriRemoteSetup();

    return () => {
      cleanup();
      interceptorInstalledRef.current = false;
    };
  }, []);

  if (localMode || isDedicatedAuthRoute(pathname)) {
    return null;
  }

  return <AuthCallback />;
}
