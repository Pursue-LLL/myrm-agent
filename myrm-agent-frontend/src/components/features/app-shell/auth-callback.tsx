'use client';

import { useEffect, useRef, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import useAuthStore from '@/store/useAuthStore';
import { toast } from '@/hooks/useToast';

/**
 * OAuth 回调处理组件
 *
 * 检测 URL 中的 token 参数，处理登录流程。
 *
 * 重要：使用 window.location.href 强制刷新页面，确保所有组件
 * 从最新的 localStorage 状态开始初始化，避免时序问题导致的 401 错误。
 *
 * Hydration 策略：
 * - 在 SSR 时返回 null，避免 useSearchParams() 导致的 hydration 错误
 * - 客户端 mount 后再处理 OAuth 回调
 */
export default function AuthCallback() {
  const [mounted, setMounted] = useState(false);

  // 客户端 mount 检测
  useEffect(() => {
    setMounted(true);
  }, []);

  // SSR 时返回 null，避免 hydration 错误
  if (!mounted) {
    return null;
  }

  return <AuthCallbackContent />;
}

/**
 * AuthCallback 的实际内容组件
 * 分离出来以确保 hooks 顺序一致
 */
function AuthCallbackContent() {
  const t = useTranslations('auth');
  const searchParams = useSearchParams();
  const router = useRouter();
  const { login, initAuth, isInitialized } = useAuthStore();
  const processedRef = useRef(false);

  useEffect(() => {
    // 初始化认证状态
    if (!isInitialized) {
      initAuth();
    }
  }, [isInitialized, initAuth]);

  useEffect(() => {
    // 防止重复处理
    if (processedRef.current) return;

    // Dedicated routes handle their own query params (exchange / provider errors).
    const pathname = window.location.pathname;
    if (
      pathname.startsWith('/auth/setup')
      || pathname.startsWith('/auth/login')
      || pathname.startsWith('/auth/oauth/callback')
      || pathname.startsWith('/auth/mcp-callback')
    ) {
      return;
    }

    const token = searchParams.get('token');
    const error = searchParams.get('error');
    const message = searchParams.get('message');

    // 处理错误
    if (error) {
      processedRef.current = true;
      toast({
        title: t('oauthErrorTitle'),
        description: message || t('oauthErrorDescription'),
        variant: 'destructive',
      });
      // 清除 URL 参数
      router.replace('/');
      return;
    }

    // 处理 token
    if (token) {
      processedRef.current = true;
      console.warn('[AuthCallback] Processing OAuth token...');

      login(token)
        .then(() => {
          console.warn('[AuthCallback] Login successful, token stored');
          toast({
            title: t('loginSuccessTitle'),
            description: t('loginSuccessDescription'),
          });
          // 使用 window.location.href 强制刷新页面
          // 这样可以确保所有组件从最新的 localStorage 状态开始初始化
          // 避免时序问题导致其他组件在 token 存储前就发起 API 请求
          window.location.href = '/';
        })
        .catch(() => {
          toast({
            title: t('loginFailedTitle'),
            description: t('tokenVerificationFailed'),
            variant: 'destructive',
          });
          router.replace('/');
        });
    }
  }, [searchParams, login, router, t]);

  return null;
}
