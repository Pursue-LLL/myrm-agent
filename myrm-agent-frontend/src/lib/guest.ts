/**
 * 认证工具函数
 *
 * 提供认证状态检查和 Token 管理功能。
 *
 * 注意：本项目没有"访客模式"：
 * - Tauri 模式：自动登录 local_user
 * - Sandbox 模式：必须 OAuth 登录
 */

import { clearAuthSessionCookie, setAuthSessionCookie } from '@/lib/auth-cookie';

const AUTH_TOKEN_KEY = 'auth_token';

/**
 * 检查当前用户是否未登录
 * - auth_token 不存在 → 未登录
 * - auth_token 以 'mock-token-' 开头 → 未登录（开发模式）
 */
export function isGuest(): boolean {
  if (typeof window === 'undefined') return true;

  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  return !token || token.startsWith('mock-token-');
}

/**
 * 检查当前用户是否已认证
 */
export function isAuthenticated(): boolean {
  return !isGuest();
}

/**
 * 获取认证 Token（仅在已认证时返回）
 */
export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;

  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (token && !token.startsWith('mock-token-')) {
    return token;
  }
  return null;
}

/**
 * 设置认证 Token
 */
export function setAuthToken(token: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(AUTH_TOKEN_KEY, token);
  if (!token.startsWith('mock-token-')) {
    setAuthSessionCookie();
  }
}

/**
 * 清除认证 Token（登出时调用）
 */
export function clearAuthToken(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(AUTH_TOKEN_KEY);
  clearAuthSessionCookie();
}
