/**
 * [INPUT]
 * - `@/lib/backend-health` (`checkBackendReadyOnce`)
 * - `@/lib/deploy-mode` (`isLocalMode`, `isRemoteGatewayActive`, `setRemoteGatewayConfig`, `getRemoteGatewayConfig`)
 * - `next-intl` (`common.configLoadError`, `common.close`, `common.remoteGateway`)
 *
 * [OUTPUT]
 * - `LocalBackendUnavailableBanner`: local 模式主内容区顶部告警条
 * - `ConfigReadinessDegradedBanner`: 配置 readiness 降级时的非阻塞告警条
 * - `isLocalBackendBannerDismissed` / `dismissLocalBackendBanner`: session dismiss SSOT
 *
 * [POS]
 * 补齐 Boot 屏被 session 跳过后仍无后端时的 setup 指引；后端恢复后自动隐藏。
 */
'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertCircle, AlertTriangle, X } from 'lucide-react';
import { checkBackendReadyOnce } from '@/lib/backend-health';
import { waitForChromeE2eBackendBinding, isChromeE2eTab } from '@/lib/local-backend-e2e-probe';
import { isLocalMode, isRemoteGatewayActive, setRemoteGatewayConfig, getRemoteGatewayConfig } from '@/lib/deploy-mode';
import { resolveLocalBackendSetupHint } from '@/lib/local-backend-dev';
import { cn } from '@/lib/utils/classnameUtils';

const DISMISS_STORAGE_KEY = 'myrm_local_backend_banner_dismissed';
const RECOVERY_POLL_INTERVAL_MS = 5000;

export function isLocalBackendBannerDismissed(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  try {
    return sessionStorage.getItem(DISMISS_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export function dismissLocalBackendBanner(): void {
  try {
    sessionStorage.setItem(DISMISS_STORAGE_KEY, '1');
  } catch {
    // sessionStorage unavailable
  }
}

interface LocalBackendUnavailableBannerProps {
  className?: string;
}

export default function LocalBackendUnavailableBanner({ className }: LocalBackendUnavailableBannerProps) {
  const tHint = useTranslations('common.configLoadError');
  const tCommon = useTranslations('common');
  const tRemote = useTranslations('common.remoteGateway');
  const [visible, setVisible] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const [isRemote, setIsRemote] = useState(false);

  const handleSwitchToLocal = useCallback(() => {
    setRemoteGatewayConfig(null);
    window.location.reload();
  }, []);

  useEffect(() => {
    const remoteActive = isRemoteGatewayActive();
    setIsRemote(remoteActive);

    if (!isLocalMode() && !remoteActive) {
      return undefined;
    }

    if (!remoteActive && isLocalBackendBannerDismissed()) {
      return undefined;
    }

    let cancelled = false;

    void (async () => {
      if (!remoteActive && isChromeE2eTab()) {
        const bound = await waitForChromeE2eBackendBinding();
        if (cancelled) {
          return;
        }
        if (!bound) {
          return;
        }
      }

      const ready = await checkBackendReadyOnce();
      if (cancelled || ready) {
        return;
      }

      if (remoteActive) {
        const cfg = getRemoteGatewayConfig();
        const host = cfg ? new URL(cfg.url).host : '';
        setHint(tRemote('unreachable', { host }));
      } else {
        const setupHint = await resolveLocalBackendSetupHint(tHint);
        setHint(setupHint);
      }

      if (!cancelled) {
        setVisible(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [tHint, tRemote]);

  useEffect(() => {
    if (!visible) {
      return undefined;
    }

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    const scheduleRecoveryCheck = () => {
      timeoutId = window.setTimeout(() => {
        void checkBackendReadyOnce().then((ready) => {
          if (cancelled) {
            return;
          }
          if (ready) {
            setVisible(false);
            return;
          }
          scheduleRecoveryCheck();
        });
      }, RECOVERY_POLL_INTERVAL_MS);
    };

    scheduleRecoveryCheck();

    return () => {
      cancelled = true;
      if (timeoutId !== undefined) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [visible]);

  const handleDismiss = useCallback(() => {
    dismissLocalBackendBanner();
    setVisible(false);
  }, []);

  if (!visible || !hint) {
    return null;
  }

  return (
    <div
      data-testid="local-backend-unavailable-banner"
      role="alert"
      className={cn(
        'mb-4 flex w-full items-start gap-3 rounded-lg border border-destructive/30',
        'bg-destructive/10 px-4 py-3 text-[13px] leading-relaxed text-destructive/90',
        'dark:border-destructive/40 dark:bg-destructive/15',
        className,
      )}
    >
      <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="whitespace-pre-line font-mono">{hint}</p>
        {isRemote && (
          <button
            type="button"
            onClick={handleSwitchToLocal}
            className="mt-2 text-xs font-medium underline underline-offset-2 hover:no-underline"
          >
            {tRemote('switchToLocal')}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={handleDismiss}
        className="flex-shrink-0 rounded p-1 text-destructive/70 transition-colors hover:bg-destructive/10 hover:text-destructive"
        aria-label={tCommon('close')}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

interface ConfigReadinessDegradedBannerProps {
  visible: boolean;
  onRetry?: () => void;
  onDismiss?: () => void;
  className?: string;
}

export function ConfigReadinessDegradedBanner({
  visible,
  onRetry,
  onDismiss,
  className,
}: ConfigReadinessDegradedBannerProps) {
  const t = useTranslations('common.readinessDegraded');
  const tCommon = useTranslations('common');

  if (!visible) {
    return null;
  }

  return (
    <div
      data-testid="config-readiness-degraded-banner"
      role="alert"
      className={cn(
        'mb-4 flex w-full items-start gap-3 rounded-lg border border-amber-500/30',
        'bg-amber-500/10 px-4 py-3 text-[13px] leading-relaxed text-amber-800',
        'dark:border-amber-400/30 dark:bg-amber-500/15 dark:text-amber-200',
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium">{t('title')}</p>
        <p className="text-amber-700/90 dark:text-amber-200/80">{t('description')}</p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-1 text-xs font-medium underline underline-offset-2 hover:no-underline"
          >
            {t('retry')}
          </button>
        ) : null}
      </div>
      {onDismiss ? (
        <button
          type="button"
          onClick={onDismiss}
          className="flex-shrink-0 rounded p-1 text-amber-700/70 transition-colors hover:bg-amber-500/10 hover:text-amber-800 dark:text-amber-200/70"
          aria-label={tCommon('close')}
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  );
}
