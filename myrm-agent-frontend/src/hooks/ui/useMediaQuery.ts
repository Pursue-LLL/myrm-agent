'use client';

import { useState, useEffect } from 'react';

/**
 * 自定义 Hook：检测媒体查询是否匹配
 * @param query CSS 媒体查询字符串，例如 '(max-width: 768px)'
 * @returns 布尔值，表示媒体查询是否匹配
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    // 服务端渲染时，window 不存在
    if (typeof window === 'undefined') return;

    const mediaQueryList = window.matchMedia(query);

    // 初始检查
    setMatches(mediaQueryList.matches);

    // 监听变化
    const listener = (event: MediaQueryListEvent) => {
      setMatches(event.matches);
    };

    // 添加监听器
    mediaQueryList.addEventListener('change', listener);

    // 清理
    return () => {
      mediaQueryList.removeEventListener('change', listener);
    };
  }, [query]);

  return matches;
}

/**
 * 预定义的断点 hooks
 */

/** 是否为移动端（宽度 <= 768px） */
export function useIsMobile(): boolean {
  return useMediaQuery('(max-width: 768px)');
}

/** 是否为平板（宽度 <= 1024px） */
export function useIsTablet(): boolean {
  return useMediaQuery('(max-width: 1024px)');
}

/** 是否为桌面端（宽度 > 1024px） */
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 1025px)');
}

/** 是否偏好减少动画 */
export function usePrefersReducedMotion(): boolean {
  return useMediaQuery('(prefers-reduced-motion: reduce)');
}

/** 是否偏好深色模式 */
export function usePrefersDarkMode(): boolean {
  return useMediaQuery('(prefers-color-scheme: dark)');
}
