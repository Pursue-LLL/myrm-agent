'use client';

import React, { memo, useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { usePathname } from 'next/navigation';
import AppLayout from './AppLayout';
import { isStandalonePath } from '@/lib/marketing-paths';
import { waitForBackendReady } from '@/lib/backend-health';
import { isTauriEnvironment } from '@/lib/tauri';
import { getReadinessStatus } from '@/services/onboarding';
import { shouldShowBootScreen } from '../features/app-shell/boot-screen';
import { useFocusedMode } from '@/hooks/useFocusedMode';
import AppShellSkeleton from '../features/app-shell/AppShellSkeleton';

const BootScreen = lazy(() => import('../features/app-shell/boot-screen'));
const OnboardingWizard = lazy(() => import('../features/onboarding/OnboardingWizard'));

interface PageLayoutProps {
  children: React.ReactNode;
}

/**
 * PageLayout - Client Component entry point
 *
 * Hydration 策略：
 * - SSR 阶段渲染 AppShellSkeleton
 * - 客户端挂载后：检查 onboarding_completed 状态
 * - 若未完成，展示 OnboardingWizard
 * - 若已完成，且为冷启动，展示 BootScreen
 * - 否则直接渲染 AppLayout
 */
const PageLayout = memo<PageLayoutProps>(({ children }) => {
  const pathname = usePathname();
  const isStandaloneRoute = isStandalonePath(pathname);
  const isFocusedMode = useFocusedMode();
  const [mounted, setMounted] = useState(false);
  const [checkingReadiness, setCheckingReadiness] = useState(true);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [showNormalBoot, setShowNormalBoot] = useState(false);

  useEffect(() => {
    setMounted(true);

    if (isStandaloneRoute || isFocusedMode) {
      setCheckingReadiness(false);
      return;
    }

    void (async () => {
      try {
        if (isTauriEnvironment()) {
          await waitForBackendReady();
        }

        const status = await getReadinessStatus();
        if (!status.onboarding_completed) {
          setNeedsOnboarding(true);
        } else if (shouldShowBootScreen()) {
          setShowNormalBoot(true);
        }
      } catch {
        if (shouldShowBootScreen()) {
          setShowNormalBoot(true);
        }
      } finally {
        setCheckingReadiness(false);
      }
    })();
  }, [isStandaloneRoute, isFocusedMode]);

  const handleOnboardingComplete = useCallback(() => {
    setNeedsOnboarding(false);
  }, []);

  const handleBootComplete = useCallback(() => {
    setShowNormalBoot(false);
  }, []);

  if (isStandaloneRoute || isFocusedMode) {
    return <>{children}</>;
  }

  if (!mounted || checkingReadiness) {
    return <AppShellSkeleton />;
  }

  if (needsOnboarding) {
    return (
      <Suspense fallback={<AppShellSkeleton />}>
        <OnboardingWizard onComplete={handleOnboardingComplete} />
      </Suspense>
    );
  }

  if (showNormalBoot) {
    return (
      <Suspense fallback={<AppShellSkeleton />}>
        <BootScreen onComplete={handleBootComplete} />
      </Suspense>
    );
  }

  return <AppLayout>{children}</AppLayout>;
});

PageLayout.displayName = 'PageLayout';

export default PageLayout;
