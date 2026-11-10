'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Zap } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { getConfigSyncManager } from '@/services/config';
import { useManagedPolicyEffective } from '@/hooks/useManagedPolicyEffective';
import { orgBlocksYoloForModel } from '@/lib/managedPolicyMatch';
import { resolveActiveModelSelection } from '@/lib/model-binding';
import useChatStore from '@/store/useChatStore';
import useProviderStore from '@/store/useProviderStore';

const nowSeconds = () => Math.floor(Date.now() / 1000);

/** Writes YOLO off into the shared configuration; the banner hides through its own subscription. */
function switchYoloOff(): void {
  const syncManager = getConfigSyncManager();
  const current = syncManager.get('securityConfig');
  if (current?.yoloModeEnabled) {
    syncManager.set('securityConfig', {
      ...current,
      yoloModeEnabled: false,
      yoloModeTimeout: undefined,
      yoloModeEnabledAt: undefined,
    });
  }
}

export default function YoloModeBanner() {
  const t = useTranslations('yoloBanner');
  const [yoloEnabled, setYoloEnabled] = useState(false);
  /** Epoch second at which the time limit runs out; null when YOLO has no time limit. */
  const [expiresAt, setExpiresAt] = useState<number | null>(null);
  const [now, setNow] = useState(nowSeconds);
  const { policy, active: mapActive } = useManagedPolicyEffective();
  const actionMode = useChatStore((state) => state.actionMode);
  const agentConfig = useChatStore((state) => state.agentConfig);
  const defaultModelConfig = useProviderStore((state) => state.defaultModelConfig);
  const providers = useProviderStore((state) => state.providers);

  const activeModelSlug = useMemo(() => {
    const selection = resolveActiveModelSelection(actionMode, agentConfig, defaultModelConfig, providers);
    return selection?.model ?? '';
  }, [actionMode, agentConfig, defaultModelConfig, providers]);

  const orgBlocksYolo = mapActive && orgBlocksYoloForModel(policy, activeModelSlug);
  // A policy that turns YOLO off outright blocks it for every model, so this is the narrower case of the above.
  const orgDisablesYolo = orgBlocksYolo && Boolean(policy.disableYolo);

  useEffect(() => {
    const syncManager = getConfigSyncManager();

    function sync() {
      const config = syncManager.get('securityConfig');
      const enabled = config?.yoloModeEnabled ?? false;
      setYoloEnabled(enabled);

      if (enabled && config?.yoloModeTimeout && config?.yoloModeEnabledAt) {
        setExpiresAt(config.yoloModeEnabledAt + config.yoloModeTimeout);
        setNow(nowSeconds());
      } else {
        setExpiresAt(null);
      }
    }

    sync();
    const unsubscribe = syncManager.subscribe('securityConfig', sync);
    return unsubscribe;
  }, []);

  // The clock is read on every tick rather than counting seconds down, so timers a browser slows in a
  // background tab cannot leave the banner behind the real time.
  const remaining = expiresAt === null ? null : Math.max(0, expiresAt - now);
  const isCountingDown = remaining !== null && remaining > 0;

  useEffect(() => {
    if (!isCountingDown) {
      return;
    }
    const timer = setInterval(() => setNow(nowSeconds()), 1000);
    return () => clearInterval(timer);
  }, [isCountingDown]);

  useEffect(() => {
    if (remaining === 0) {
      switchYoloOff();
    }
  }, [remaining]);

  if (!yoloEnabled || remaining === 0) {
    return null;
  }

  const countdownText = remaining !== null ? ` (${formatCountdown(remaining)})` : '';
  const bannerMessage = orgDisablesYolo
    ? t('orgGlobalDisabledMessage', {
        default: 'YOLO is disabled by your organization policy.',
      })
    : orgBlocksYolo
      ? t('orgConstrainedMessage', {
          default: "YOLO is on, but your organization's policy still requires approval for this agent's model.",
        })
      : t('message', { default: 'YOLO Mode Active – All tools auto-approved' });

  return (
    <div
      className={`flex items-center justify-between gap-2 px-4 py-1.5 border-b ${
        orgBlocksYolo
          ? 'bg-amber-500/15 border-amber-500/30 text-amber-800 dark:text-amber-300'
          : 'bg-amber-500/10 border-amber-500/20 text-amber-700 dark:text-amber-400'
      }`}
    >
      <div className="flex items-center gap-2 min-w-0">
        {orgBlocksYolo ? (
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <Zap className="h-3.5 w-3.5 shrink-0 fill-current" />
        )}
        <span className="text-xs font-medium truncate">
          {bannerMessage}
          {countdownText}
        </span>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs text-amber-700 hover:text-amber-900 hover:bg-amber-500/20 dark:text-amber-400 dark:hover:text-amber-200 dark:hover:bg-amber-500/20 shrink-0"
        onClick={switchYoloOff}
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
