'use client';

/**
 * [INPUT]
 * @/store/useProviderBalanceStore (POS: gauge state for current provider)
 * @/store/useProviderStore (POS: defaultModelConfig / providers)
 * @/store/useChatStore (POS: agentConfig & updateAgentConfig)
 * next-intl (POS: i18n copy)
 *
 * [OUTPUT]
 * ProviderLowBalanceWarningHUD: non-blocking floating banner warning about depleted provider quota
 *
 * [POS]
 * Renders non-intrusive warning when the current active provider is in 'critical' or 'warning'
 * balance status. Provides a 1-click fallback model switch button to prevent mid-task breakage.
 */

import { memo, useState, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, ArrowRight, X } from 'lucide-react';
import useProviderBalanceStore from '@/store/useProviderBalanceStore';
import useProviderStore from '@/store/useProviderStore';
import useChatStore from '@/store/useChatStore';
import { resolveActiveModelSelection } from '@/lib/model-binding';
import { cn } from '@/lib/utils/classnameUtils';

interface ProviderLowBalanceWarningHUDProps {
  currentProviderId?: string | null;
  className?: string;
}

export const ProviderLowBalanceWarningHUD = memo<ProviderLowBalanceWarningHUDProps>(
  ({ currentProviderId, className }) => {
    const t = useTranslations('settings.providerBalance');
    const [isDismissed, setIsDismissed] = useState(false);

    const getGauge = useProviderBalanceStore((state) => state.getGauge);
    const defaultModelConfig = useProviderStore((state) => state.defaultModelConfig);
    const providers = useProviderStore((state) => state.providers);
    const setBaseModel = useProviderStore((state) => state.setBaseModel);
    const actionMode = useChatStore((state) => state.actionMode);
    const agentConfig = useChatStore((state) => state.agentConfig);
    const updateAgentConfig = useChatStore((state) => state.updateAgentConfig);

    const activeSelection = useMemo(() => {
      if (currentProviderId) return null;
      if (!defaultModelConfig?.baseModel?.primary) return null;
      return resolveActiveModelSelection(actionMode, agentConfig, defaultModelConfig, providers);
    }, [currentProviderId, actionMode, agentConfig, defaultModelConfig, providers]);

    const targetProviderId = currentProviderId ?? activeSelection?.providerId;
    const gauge = getGauge(targetProviderId);

    // Identify candidate safety fallback
    const safetyFallback =
      defaultModelConfig?.safetyFallbackModelSelection ||
      defaultModelConfig?.baseModelFallback ||
      defaultModelConfig?.liteModel;

    const handleSwitchToSafetyFallback = useCallback(() => {
      if (!safetyFallback?.providerId || !safetyFallback?.model) return;
      if (actionMode === 'fast' && typeof setBaseModel === 'function') {
        setBaseModel(safetyFallback);
      } else if (typeof updateAgentConfig === 'function') {
        updateAgentConfig({
          modelSelection: {
            providerId: safetyFallback.providerId,
            model: safetyFallback.model,
          },
        });
      }
      setIsDismissed(true);
    }, [safetyFallback, actionMode, updateAgentConfig, setBaseModel]);

    if (!gauge || isDismissed) return null;
    if (gauge.status !== 'warning' && gauge.status !== 'critical') return null;

    const isCritical = gauge.status === 'critical';

    return (
      <div
        className={cn(
          'flex items-center justify-between gap-3 px-3 py-2 rounded-lg border text-xs shadow-sm transition-all backdrop-blur-md',
          isCritical
            ? 'bg-rose-500/10 border-rose-500/30 text-rose-700 dark:text-rose-300'
            : 'bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-300',
          className,
        )}
        data-testid="provider-low-balance-warning-hud"
      >
        <div className="flex items-center gap-2 min-w-0">
          <AlertTriangle className={cn('h-4 w-4 shrink-0', isCritical ? 'text-rose-500' : 'text-amber-500')} />
          <div className="truncate">
            <span className="font-semibold">{t(isCritical ? 'hudCriticalTitle' : 'hudWarningTitle')}: </span>
            <span>
              {gauge.details ||
                t('hudBalanceDepletedDesc', {
                  provider: gauge.provider_id,
                  balance: gauge.balance !== null ? `${gauge.balance.toFixed(2)} ${gauge.currency}` : '',
                })}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {safetyFallback && safetyFallback.providerId !== currentProviderId && (
            <button
              type="button"
              onClick={handleSwitchToSafetyFallback}
              className={cn(
                'flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium border transition-colors hover:opacity-90',
                isCritical
                  ? 'bg-rose-500 text-white border-rose-600 shadow-[0_0_8px_rgba(244,63,94,0.4)]'
                  : 'bg-amber-500 text-white border-amber-600',
              )}
            >
              <span>{t('hudSwitchToFallback')}</span>
              <ArrowRight className="h-3 w-3" />
            </button>
          )}
          <button
            type="button"
            onClick={() => setIsDismissed(true)}
            className="p-1 rounded hover:bg-black/5 dark:hover:bg-white/5 opacity-60 hover:opacity-100 transition-opacity"
            aria-label={t('dismiss')}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    );
  },
);

ProviderLowBalanceWarningHUD.displayName = 'ProviderLowBalanceWarningHUD';
export default ProviderLowBalanceWarningHUD;
