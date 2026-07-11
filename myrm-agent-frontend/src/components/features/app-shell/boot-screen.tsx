'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import BrandLogo from '@/components/features/app-shell/BrandLogo';
import { waitForBackendReady } from '@/lib/backend-health';
import { resolveLocalBackendSetupHint } from '@/lib/local-backend-dev';
import { markBootScreenShown } from '@/components/features/app-shell/boot-screen-gate';
import { isLocalMode } from '@/lib/deploy-mode';
import { cn } from '@/lib/utils/classnameUtils';

const STEP_INTERVAL_MS = 120;
const FADE_START_DELAY_MS = 340;
const FADE_DURATION_MS = 400;

interface BootScreenProps {
  onComplete: () => void;
}

export default function BootScreen({ onComplete }: BootScreenProps) {
  const t = useTranslations('boot');
  const tSetupHint = useTranslations('common.configLoadError');
  const [visibleSteps, setVisibleSteps] = useState(0);
  const [logoVisible, setLogoVisible] = useState(false);
  const [titleVisible, setTitleVisible] = useState(false);
  const [fadeOut, setFadeOut] = useState(false);
  const [backendUnavailable, setBackendUnavailable] = useState(false);
  const [backendSetupHint, setBackendSetupHint] = useState<string | null>(null);
  const completedRef = useRef(false);
  const backendGateOpenRef = useRef(false);
  const exitRequestedRef = useRef(false);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const steps = [t('step.loadingTheme'), t('step.syncingSettings'), t('step.initServices'), t('step.ready')];

  const tryFinish = useCallback(() => {
    if (completedRef.current) return;
    if (!backendGateOpenRef.current || !exitRequestedRef.current) return;
    completedRef.current = true;
    markBootScreenShown();
    setFadeOut(true);
    const fadeTimer = setTimeout(onComplete, FADE_DURATION_MS);
    timersRef.current.push(fadeTimer);
  }, [onComplete]);

  const requestExit = useCallback(() => {
    exitRequestedRef.current = true;
    tryFinish();
  }, [tryFinish]);

  useEffect(() => {
    if (!isLocalMode()) {
      backendGateOpenRef.current = true;
      tryFinish();
      return undefined;
    }

    const abortController = new AbortController();

    void waitForBackendReady({ signal: abortController.signal })
      .then(async (ready) => {
        if (!ready) {
          setBackendUnavailable(true);
          const hint = await resolveLocalBackendSetupHint(tSetupHint);
          setBackendSetupHint(hint);
        }
      })
      .finally(() => {
        backendGateOpenRef.current = true;
        tryFinish();
      });

    return () => {
      abortController.abort();
    };
  }, [tryFinish, tSetupHint]);

  useEffect(() => {
    const timers = timersRef.current;

    timers.push(setTimeout(() => setLogoVisible(true), 80));
    timers.push(setTimeout(() => setTitleVisible(true), 300));

    steps.forEach((_, i) => {
      timers.push(setTimeout(() => setVisibleSteps(i + 1), 500 + i * STEP_INTERVAL_MS));
    });

    const autoFinishDelay = 500 + steps.length * STEP_INTERVAL_MS + FADE_START_DELAY_MS;
    timers.push(setTimeout(requestExit, autoFinishDelay));

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') requestExit();
    };
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      timers.forEach(clearTimeout);
      timersRef.current = [];
      window.removeEventListener('keydown', handleKeyDown);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestExit]);

  return (
    <div
      data-testid="boot-screen"
      className={cn(
        'fixed inset-0 z-50 flex flex-col items-center justify-center',
        'bg-background select-none cursor-pointer',
        'transition-opacity ease-out',
        fadeOut ? 'opacity-0' : 'opacity-100',
      )}
      style={{ transitionDuration: `${FADE_DURATION_MS}ms` }}
      onClick={requestExit}
      role="presentation"
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        <div className="absolute -top-24 left-1/4 h-72 w-72 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute bottom-0 right-1/4 h-64 w-64 rounded-full bg-accent-warm/10 blur-3xl" />
      </div>

      <div className="relative flex flex-col items-center gap-3">
        <div
          className={cn(
            'transition-all duration-500 ease-out',
            logoVisible ? 'opacity-100 scale-100' : 'opacity-0 scale-90',
          )}
        >
          <BrandLogo size={56} priority className="w-12 h-12 sm:w-14 sm:h-14" />
        </div>

        <div
          className={cn(
            'text-lg sm:text-xl font-semibold transition-all duration-400 ease-out',
            titleVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-1',
            visibleSteps >= steps.length ? 'brand-gradient-text' : 'text-foreground/80',
          )}
        >
          {t('title')}
        </div>
      </div>

      <div className="mt-8 w-[280px] sm:w-[320px] space-y-1.5 px-4">
        {steps.slice(0, visibleSteps).map((step, i) => {
          const isLast = i === steps.length - 1;
          const isCurrent = i === visibleSteps - 1 && !isLast;

          return (
            <div
              key={i}
              className={cn(
                'flex items-center gap-2 text-[13px] leading-relaxed transition-opacity duration-200',
                isLast ? 'brand-gradient-text font-medium' : 'text-muted-foreground',
              )}
            >
              {isCurrent ? (
                <span className="w-3 h-3 flex items-center justify-center">
                  <span
                    className={cn(
                      'w-1.5 h-1.5 rounded-full animate-pulse',
                      i % 2 === 0 ? 'bg-primary' : 'bg-accent-warm',
                    )}
                  />
                </span>
              ) : (
                <span className="w-3 h-3 flex items-center justify-center text-accent-warm">
                  <svg viewBox="0 0 16 16" fill="none" className="w-3 h-3">
                    <path
                      d="M3 8l3.5 3.5L13 5"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
              )}
              <span>{step}</span>
            </div>
          );
        })}
      </div>

      {backendUnavailable && backendSetupHint && isLocalMode() ? (
        <p
          className="mt-6 max-w-md px-6 text-center text-[13px] leading-relaxed text-destructive/90 whitespace-pre-line font-mono"
          data-testid="boot-backend-setup-hint"
        >
          {backendSetupHint}
        </p>
      ) : null}

      <div
        className={cn(
          'absolute bottom-6 text-[12px] text-muted-foreground/50',
          'transition-opacity duration-300',
          visibleSteps > 0 ? 'opacity-100' : 'opacity-0',
        )}
      >
        {t('skipHint')}
      </div>
    </div>
  );
}
