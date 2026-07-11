'use client';

import React, { memo, useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { usePathname } from 'next/navigation';
import AppLayout from './AppLayout';
import { isStandalonePath } from '@/lib/marketing-paths';
import { waitForBackendReady } from '@/lib/backend-health';
import { isTauriEnvironment } from '@/lib/tauri';
import { getReadinessStatus, type ReadinessResponse } from '@/services/onboarding';
import { shouldShowBootScreen } from '../features/app-shell/boot-screen';
import { useFocusedMode } from '@/hooks/useFocusedMode';
import AppShellSkeleton from '../features/app-shell/AppShellSkeleton';

const READINESS_GATE_TIMEOUT_MS = 3_000;

const BootScreen = lazy(() => import('../features/app-shell/boot-screen'));
const OnboardingWizard = lazy(() => import('../features/onboarding/OnboardingWizard'));

async function resolveReadinessGate(): Promise<ReadinessResponse | null> {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      getReadinessStatus(),
      new Promise<null>((resolve) => {
        timeoutId = setTimeout(() => resolve(null), READINESS_GATE_TIMEOUT_MS);
      }),
    ]);
  } finally {
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId);
    }
  }
}

interface PageLayoutProps {
  children: React.ReactNode;
}

/**
 * PageLayout - Client Component entry point
 *
 * Shell-first: AppLayout mounts immediately after hydration; readiness runs in the
 * background. Onboarding and boot screens render as full-screen overlays.
 */
const PageLayout = memo<PageLayoutProps>(({ children }) => {
  const pathname = usePathname();
  const isStandaloneRoute = isStandalonePath(pathname);
  const isFocusedMode = useFocusedMode();
  const [mounted, setMounted] = useState(false);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [showNormalBoot, setShowNormalBoot] = useState(false);
  const [readinessDegraded, setReadinessDegraded] = useState(false);

  const runReadinessGate = useCallback(async () => {
    try {
      if (isTauriEnvironment()) {
        await waitForBackendReady();
      }

      const status = await resolveReadinessGate();
      if (status?.degraded) {
        setReadinessDegraded(true);
      } else {
        setReadinessDegraded(false);
      }

      if (status && !status.onboarding_completed) {
        setNeedsOnboarding(true);
        setShowNormalBoot(false);
      } else if (status?.onboarding_completed && shouldShowBootScreen()) {
        setShowNormalBoot(true);
        setNeedsOnboarding(false);
      }
    } catch {
      setReadinessDegraded(true);
      if (shouldShowBootScreen()) {
        setShowNormalBoot(true);
      }
    }
  }, []);

  useEffect(() => {
    setMounted(true);

    if (isStandaloneRoute || isFocusedMode) {
      return;
    }

    void runReadinessGate();
  }, [isStandaloneRoute, isFocusedMode, runReadinessGate]);

  const handleOnboardingComplete = useCallback(() => {
    setNeedsOnboarding(false);
  }, []);

  const handleBootComplete = useCallback(() => {
    setShowNormalBoot(false);
  }, []);

  const handleRetryReadiness = useCallback(() => {
    void runReadinessGate();
  }, [runReadinessGate]);

  if (isStandaloneRoute || isFocusedMode) {
    return <>{children}</>;
  }

  if (!mounted) {
    return <AppShellSkeleton />;
  }

  return (
    <>
      <AppLayout
        configReadinessDegraded={readinessDegraded}
        onRetryConfigReadiness={handleRetryReadiness}
      >
        {children}
      </AppLayout>

      {needsOnboarding && (
        <Suspense fallback={<AppShellSkeleton />}>
          <OnboardingWizard onComplete={handleOnboardingComplete} />
        </Suspense>
      )}

      {showNormalBoot && !needsOnboarding && (
        <Suspense fallback={<AppShellSkeleton />}>
          <BootScreen onComplete={handleBootComplete} />
        </Suspense>
      )}
    </>
  );
});

PageLayout.displayName = 'PageLayout';

export default PageLayout;
