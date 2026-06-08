'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Zap } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { getConfigSyncManager } from '@/services/config';

export default function YoloModeBanner() {
  const t = useTranslations('yoloBanner');
  const [yoloEnabled, setYoloEnabled] = useState(false);

  useEffect(() => {
    const syncManager = getConfigSyncManager();
    const config = syncManager.get('securityConfig');
    setYoloEnabled(config?.yoloModeEnabled ?? false);

    const unsubscribe = syncManager.subscribe('securityConfig', (_key, value) => {
      setYoloEnabled(value?.yoloModeEnabled ?? false);
    });

    return unsubscribe;
  }, []);

  const handleDisable = useCallback(() => {
    const syncManager = getConfigSyncManager();
    const current = syncManager.get('securityConfig');
    if (current) {
      syncManager.set('securityConfig', { ...current, yoloModeEnabled: false });
    }
    setYoloEnabled(false);
  }, []);

  if (!yoloEnabled) return null;

  return (
    <div className="flex items-center justify-between gap-2 px-4 py-1.5 bg-amber-500/10 border-b border-amber-500/20 text-amber-700 dark:text-amber-400">
      <div className="flex items-center gap-2 min-w-0">
        <Zap className="h-3.5 w-3.5 shrink-0 fill-current" />
        <span className="text-xs font-medium truncate">
          {t('message', { default: 'YOLO Mode Active – All tools auto-approved' })}
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
