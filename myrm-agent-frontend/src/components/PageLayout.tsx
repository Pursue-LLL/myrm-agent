'use client';

import React, { memo, useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { usePathname } from 'next/navigation';
import { AppLayout } from './layout';
import { shouldShowBootScreen } from './ui/boot-screen';
import { isStandalonePath } from '@/lib/marketing-paths';

const BootScreen = lazy(() => import('./ui/boot-screen'));

interface PageLayoutProps {
  children: React.ReactNode;
}

/**
 * PageLayout - Client Component entry point
 *
 * Hydration 策略：
 * - SSR 阶段返回 null（不渲染任何内容）
 * - 客户端挂载后：若为冷启动则展示 BootScreen，否则直接渲染 AppLayout
 * - 从根本上消除 Next.js 对 Client Component 的 Suspense 边界
 */
const PageLayout = memo<PageLayoutProps>(({ children }) => {
  const pathname = usePathname();
  const isStandaloneRoute = isStandalonePath(pathname);
  const [mounted, setMounted] = useState(false);
  const [booting, setBooting] = useState(
    () => typeof window !== 'undefined' && !isStandalonePath(window.location.pathname) && shouldShowBootScreen(),
  );

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleBootComplete = useCallback(() => {
    setBooting(false);
  }, []);

  if (isStandaloneRoute) {
    return <>{children}</>;
  }

  if (!mounted) {
    return null;
  }

  if (booting) {
    return (
      <Suspense fallback={null}>
        <BootScreen onComplete={handleBootComplete} />
      </Suspense>
    );
  }

  return <AppLayout>{children}</AppLayout>;
});

PageLayout.displayName = 'PageLayout';

export default PageLayout;
