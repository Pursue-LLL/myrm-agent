'use client';

import React, { memo, useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { usePathname } from 'next/navigation';
import { MotionConfig } from 'framer-motion';
import AppLayout from './AppLayout';
import { isStandalonePath } from '@/lib/marketing-paths';
import { ensureLocalBackendReady } from '@/lib/backend-health';
import { isTauriEnvironment } from '@/lib/tauri';
import { isSandbox } from '@/lib/deploy-mode';
import { getReadinessStatus, type ReadinessResponse } from '@/services/onboarding';
import { shouldShowBootScreen } from '@/components/features/app-shell/boot-screen-gate';
import { useFocusedMode } from '@/hooks/ui/useFocusedMode';
import AppShellSkeleton from '../features/app-shell/AppShellSkeleton';

const READINESS_GATE_TIMEOUT_MS = 3_000;

function localhostSuspenseFallback(): React.ReactNode {
  if (process.env.NODE_ENV === 'development') {
    return null;
  }
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host === '127.0.0.1' || host === 'localhost') {
      return null;
    }
  }
  return <AppShellSkeleton />;
}

const BootScreen = lazy(() => import('../features/app-shell/boot-screen').then((mod) => ({ default: mod.default })));
const OnboardingWizard = lazy(() =>
  import('../features/onboarding/OnboardingWizard').then((mod) => ({ default: mod.default })),
);

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
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [showNormalBoot, setShowNormalBoot] = useState(false);
  const [readinessDegraded, setReadinessDegraded] = useState(false);

  const runReadinessGate = useCallback(async () => {
    try {
      if (isTauriEnvironment()) {
        await ensureLocalBackendReady();
      }

      const status = await resolveReadinessGate();
      if (status?.degraded) {
        setReadinessDegraded(true);
      } else {
        setReadinessDegraded(false);
      }

      // Only a hosted sandbox runs the first-run wizard; local installs go straight to the home page,
      // where NoProviderBanner asks for the one thing they need (a model provider).
      if (status && !status.onboarding_completed && isSandbox()) {
        setNeedsOnboarding(true);
        setShowNormalBoot(false);
      } else if (status && shouldShowBootScreen()) {
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

  const content =
    isStandaloneRoute || isFocusedMode ? (
      children
    ) : (
      <>
        <AppLayout configReadinessDegraded={readinessDegraded} onRetryConfigReadiness={handleRetryReadiness}>
          {children}
        </AppLayout>

        {needsOnboarding && (
          <Suspense fallback={localhostSuspenseFallback()}>
            <OnboardingWizard onComplete={handleOnboardingComplete} />
          </Suspense>
        )}

        {showNormalBoot && !needsOnboarding && (
          <Suspense fallback={localhostSuspenseFallback()}>
            <BootScreen onComplete={handleBootComplete} />
          </Suspense>
        )}
      </>
    );

  // framer-motion drives transform and opacity through the Web Animations API, so the global
  // `prefers-reduced-motion` CSS block cannot reach it. `reducedMotion="user"` makes framer follow
  // the same OS setting: positional animation collapses to instant while opacity fades stay, so a
  // state change remains legible instead of the element simply jumping.
  return <MotionConfig reducedMotion="user">{content}</MotionConfig>;
});

PageLayout.displayName = 'PageLayout';

export default PageLayout;
