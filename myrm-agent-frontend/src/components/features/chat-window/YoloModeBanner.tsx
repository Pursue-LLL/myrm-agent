'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Zap } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { getConfigSyncManager } from '@/services/config';

export default function YoloModeBanner() {
  const t = useTranslations('yoloBanner');
  const [yoloEnabled, setYoloEnabled] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const syncManager = getConfigSyncManager();

    function sync() {
      const config = syncManager.get('securityConfig');
      const enabled = config?.yoloModeEnabled ?? false;
      setYoloEnabled(enabled);

      if (enabled && config?.yoloModeTimeout && config?.yoloModeEnabledAt) {
        const elapsed = Math.floor(Date.now() / 1000) - config.yoloModeEnabledAt;
        const left = Math.max(0, config.yoloModeTimeout - elapsed);
        setRemaining(Math.ceil(left));
      } else {
        setRemaining(null);
      }
    }

    sync();
    const unsubscribe = syncManager.subscribe('securityConfig', sync);
    return unsubscribe;
  }, []);

  const isCountingDown = remaining !== null && remaining > 0;

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);

    if (isCountingDown) {
      timerRef.current = setInterval(() => {
        setRemaining((prev) => {
          if (prev === null || prev <= 1) {
            if (timerRef.current) clearInterval(timerRef.current);
            const syncManager = getConfigSyncManager();
            const config = syncManager.get('securityConfig');
            if (config) {
              syncManager.set('securityConfig', {
                ...config,
                yoloModeEnabled: false,
                yoloModeTimeout: undefined,
                yoloModeEnabledAt: undefined,
              });
            }
            setYoloEnabled(false);
            return null;
          }
          return prev - 1;
        });
      }, 1000);
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isCountingDown]);

  const handleDisable = useCallback(() => {
    const syncManager = getConfigSyncManager();
    const current = syncManager.get('securityConfig');
    if (current) {
      syncManager.set('securityConfig', {
        ...current,
        yoloModeEnabled: false,
        yoloModeTimeout: undefined,
        yoloModeEnabledAt: undefined,
      });
    }
    setYoloEnabled(false);
    setRemaining(null);
  }, []);

  if (!yoloEnabled) return null;

  const countdownText = remaining !== null ? ` (${formatCountdown(remaining)})` : '';

  return (
    <div className="flex items-center justify-between gap-2 px-4 py-1.5 bg-amber-500/10 border-b border-amber-500/20 text-amber-700 dark:text-amber-400">
      <div className="flex items-center gap-2 min-w-0">
        <Zap className="h-3.5 w-3.5 shrink-0 fill-current" />
        <span className="text-xs font-medium truncate">
          {t('message', { default: 'YOLO Mode Active – All tools auto-approved' })}
          {countdownText}
        </span>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs text-amber-700 hover:text-amber-900 hover:bg-amber-500/20 dark:text-amber-400 dark:hover:text-amber-200 dark:hover:bg-amber-500/20 shrink-0"
        onClick={handleDisable}
      >
        <AlertTriangle className="h-3 w-3 mr-1" />
        {t('disable', { default: 'Disable' })}
      </Button>
    </div>
  );
}

function formatCountdown(seconds: number): string {
  if (seconds >= 3600) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  }
  if (seconds >= 60) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s`;
  }
  return `${seconds}s`;
}
