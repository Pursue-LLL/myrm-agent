/**
 * [INPUT]
 * - `@/services/config/ConfigSyncManager` (`getConfigSyncManager`: `initialize`, `getUnreadableKeys`, `subscribe`)
 * - `@/services/config/types` (`ALL_CONFIG_KEYS`: every key the banner re-checks when its config arrives or is saved)
 * - `next-intl` (`common.configUnreadable`, `common.close`)
 *
 * [OUTPUT]
 * - `ConfigUnreadableBanner`: AppLayout top alert while a saved config is sealed under a key this device no longer has
 *
 * [POS]
 * Explains why saved credentials show up empty, so the user does not read it as "nothing configured" and overwrite it.
 */
'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { getConfigSyncManager } from '@/services/config/ConfigSyncManager';
import { ALL_CONFIG_KEYS, type ConfigKey } from '@/services/config/types';

function useUnreadableConfigKeys(): ConfigKey[] {
  const [keys, setKeys] = useState<ConfigKey[]>([]);

  useEffect(() => {
    const manager = getConfigSyncManager();
    const unsubscribers: Array<() => void> = [];
    let active = true;

    const refresh = () => {
      if (active) {
        setKeys(manager.getUnreadableKeys());
      }
    };

    void manager.initialize().then(() => {
      if (!active) {
        return;
      }
      refresh();
      // Cloud loads the core configs first and preloads the rest afterwards, so a sealed config can arrive after the
      // first refresh; a key also leaves the list once the user saves it. Both notify that key's subscribers.
      for (const key of ALL_CONFIG_KEYS) {
        unsubscribers.push(manager.subscribe(key, refresh));
      }
    });

    return () => {
      active = false;
      unsubscribers.forEach((unsubscribe) => unsubscribe());
    };
  }, []);

  return keys;
}

interface ConfigUnreadableBannerProps {
  className?: string;
}

export default function ConfigUnreadableBanner({ className }: ConfigUnreadableBannerProps) {
  const t = useTranslations('common.configUnreadable');
  const tCommon = useTranslations('common');
  const keys = useUnreadableConfigKeys();
  const [dismissed, setDismissed] = useState(false);

  if (keys.length === 0 || dismissed) {
    return null;
  }

  return (
    <div
      data-testid="config-unreadable-banner"
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
      </div>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="flex-shrink-0 rounded p-1 text-amber-700/70 transition-colors hover:bg-amber-500/10 hover:text-amber-800 dark:text-amber-200/70"
        aria-label={tCommon('close')}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
