'use client';

/**
 * [INPUT]
 * - beforeinstallprompt event
 * - window.matchMedia('(display-mode: standalone)')
 * - navigator.userAgent (iOS vs Android detection)
 *
 * [OUTPUT]
 * - MobilePwaInstallGuide: Native PWA installation guidance drawer/banner for standalone thin-client parity
 *
 * [POS]
 * Mobile PWA installation discovery banner providing Safari Add-to-Home and Chrome install-prompt flows.
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconArrowRight,
  IconCheck,
  IconSparkles,
  IconX,
} from '@/components/features/icons/PremiumIcons';

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

const DISMISS_STORAGE_KEY = 'myrm_pwa_install_dismissed_until';
const DISMISS_DURATION_DAYS = 7;

export function MobilePwaInstallGuide() {
  const t = useTranslations('mobileShell');
  const [visible, setVisible] = useState<boolean>(false);
  const [platform, setPlatform] = useState<'ios' | 'android' | 'other'>('other');
  const [installPromptEvent, setInstallPromptEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [stepModalOpen, setStepModalOpen] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    // If already in standalone mode, do not show guide
    const isStandalone =
      (typeof window.matchMedia === 'function' && window.matchMedia('(display-mode: standalone)').matches) ||
      ('standalone' in window.navigator && Boolean((window.navigator as unknown as { standalone: boolean }).standalone));

    if (isStandalone) {
      return;
    }

    // Check dismissal timestamp
    const dismissedUntil = localStorage.getItem(DISMISS_STORAGE_KEY);
    if (dismissedUntil && Number(dismissedUntil) > Date.now()) {
      return;
    }

    const ua = window.navigator.userAgent.toLowerCase();
    const isIOS = /iphone|ipad|ipod/.test(ua);
    const isAndroid = /android/.test(ua);

    if (isIOS) {
      setPlatform('ios');
      setVisible(true);
    } else if (isAndroid) {
      setPlatform('android');
      setVisible(true);
    }

    const handleBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setInstallPromptEvent(e as BeforeInstallPromptEvent);
      setVisible(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    };
  }, []);

  const handleDismiss = useCallback(() => {
    setVisible(false);
    setStepModalOpen(false);
    const expireTime = Date.now() + DISMISS_DURATION_DAYS * 24 * 60 * 60 * 1000;
    try {
      localStorage.setItem(DISMISS_STORAGE_KEY, String(expireTime));
    } catch {
      // Ignore storage errors in privacy mode
    }
  }, []);

  const handleInstallClick = useCallback(async () => {
    if (platform === 'ios') {
      setStepModalOpen(true);
      return;
    }

    if (installPromptEvent) {
      await installPromptEvent.prompt();
      const choice = await installPromptEvent.userChoice;
      if (choice.outcome === 'accepted') {
        setVisible(false);
      }
    } else {
      setStepModalOpen(true);
    }
  }, [installPromptEvent, platform]);

  if (!visible) {
    return null;
  }

  return (
    <>
      <aside
        aria-label={t('installGuideTitle')}
        className="fixed bottom-20 inset-x-4 z-40 mx-auto max-w-md rounded-2xl border border-primary/25 bg-background/95 p-3.5 shadow-xl backdrop-blur-md transition-all duration-300"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <IconSparkles className="h-5 w-5" />
            </div>
            <div>
              <h4 className="text-xs font-semibold text-foreground">
                {t('installGuideTitle')}
              </h4>
              <p className="mt-0.5 text-[11px] text-muted-foreground leading-relaxed">
                {t('installGuideSubtitle')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleDismiss}
            aria-label={t('dismiss')}
            className="rounded-lg p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <IconX className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-3 flex items-center justify-end gap-2 border-t border-border/40 pt-2.5">
          <button
            type="button"
            onClick={handleDismiss}
            className="rounded-lg px-2.5 py-1 text-[11px] font-medium text-muted-foreground hover:text-foreground"
          >
            {t('remindLater')}
          </button>
          <button
            type="button"
            onClick={() => void handleInstallClick()}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-[11px] font-semibold text-primary-foreground shadow-xs transition-opacity hover:opacity-90"
          >
            <span>{platform === 'ios' ? t('viewSteps') : t('installNow')}</span>
            <IconArrowRight className="h-3 w-3" />
          </button>
        </div>
      </aside>

      {stepModalOpen && (
        <dialog
          open
          aria-modal="true"
          aria-label={t('iosStepsTitle')}
          className="fixed inset-0 z-50 m-0 flex h-full w-full max-h-none max-w-none items-end justify-center bg-black/60 p-4 backdrop-blur-xs border-none"
        >
          <div className="w-full max-w-md rounded-2xl border border-border bg-background p-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-border/40 pb-3">
              <h3 className="text-sm font-semibold text-foreground">
                {platform === 'ios' ? t('iosStepsTitle') : t('installStepsTitle')}
              </h3>
              <button
                type="button"
                onClick={() => setStepModalOpen(false)}
                className="rounded-lg p-1 text-muted-foreground hover:text-foreground"
              >
                <IconX className="h-4 w-4" />
              </button>
            </div>

            <ol className="mt-4 space-y-3 text-xs text-muted-foreground">
              {platform === 'ios' ? (
                <>
                  <li className="flex items-start gap-2.5">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
                      1
                    </span>
                    <span>{t('iosStep1')}</span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
                      2
                    </span>
                    <span>{t('iosStep2')}</span>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
                      3
                    </span>
                    <span>{t('iosStep3')}</span>
                  </li>
                </>
              ) : (
                <li className="flex items-start gap-2.5">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
                    1
                  </span>
                  <span>{t('androidStepManual')}</span>
                </li>
              )}
            </ol>

            <button
              type="button"
              onClick={() => setStepModalOpen(false)}
              className="mt-5 flex w-full items-center justify-center gap-1.5 rounded-xl bg-secondary py-2 text-xs font-semibold text-foreground hover:bg-secondary/80"
            >
              <IconCheck className="h-3.5 w-3.5 text-emerald-500" />
              <span>{t('gotIt')}</span>
            </button>
          </div>
        </dialog>
      )}
    </>
  );
}
