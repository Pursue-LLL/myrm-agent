'use client';

import { memo, useEffect, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import {
  IconBrain,
  IconCode,
  IconCpu,
  IconFileText,
  IconRoute,
  IconShield,
  IconZap,
} from '@/components/features/icons/PremiumIcons';
import useProviderStore from '@/store/useProviderStore';
import SettingsSection from '../sections/SettingsSection';
import { ModelCardTitle } from './ModelCardParts';
import ModelSelectRow from './ModelSelectRow';
import type { ModelSlotId } from './modelSlots';

const SMART_ROUTING_SECTION_ID = 'smart-routing-section';

/** Scrolls to the routing card and rings it briefly when the page is opened with `?focus=routing`. */
export function useFocusRoutingDeeplink(): void {
  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    if (new URLSearchParams(window.location.search).get('focus') !== 'routing') {
      return;
    }
    const timer = setTimeout(() => {
      const el = document.getElementById(SMART_ROUTING_SECTION_ID);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('ring-2', 'ring-emerald-500/50', 'transition-all', 'duration-500');
        setTimeout(() => {
          el.classList.remove('ring-2', 'ring-emerald-500/50');
        }, 2500);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, []);
}

interface RoutingTierCardProps {
  icon: ReactNode;
  title: string;
  description: string;
  primaryLabel: string;
  primarySlot: ModelSlotId;
  fallbackSlot: ModelSlotId;
  children?: ReactNode;
}

/** One routing tier: the model that handles it, its nested fallback and any tier-specific control. */
function RoutingTierCard({
  icon,
  title,
  description,
  primaryLabel,
  primarySlot,
  fallbackSlot,
  children,
}: RoutingTierCardProps) {
  const t = useTranslations('settings.defaultModel');
  return (
    <div className="p-5 bg-background/50 rounded-xl border border-border/50">
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <span className="text-sm font-medium text-foreground">{title}</span>
      </div>
      <p className="text-xs text-muted-foreground mb-4">{description}</p>
      <div className="space-y-4">
        <ModelSelectRow slot={primarySlot} label={primaryLabel} />
        <div className="pl-4 border-l-2 border-border/30">
          <div className="flex items-center gap-2 mb-2">
            <IconShield className="w-3.5 h-3.5 text-sky-500" />
            <span className="text-xs font-medium text-muted-foreground">{t('fallbackModel')}</span>
          </div>
          <ModelSelectRow slot={fallbackSlot} label={t('selectFallbackModel')} withConfigure={false} />
        </div>
        {children}
      </div>
    </div>
  );
}

/** Smart routing: sends light, reasoning, code and long-document requests to dedicated models. */
const SmartRoutingCard = memo(() => {
  const t = useTranslations('settings.defaultModel');
  const { isRoutingEnabled, autoMoaReasoning, setRoutingEnabled, setAutoMoaReasoning } = useProviderStore(
    useShallow((state) => ({
      isRoutingEnabled: state.defaultModelConfig.routingConfig?.enabled ?? true,
      autoMoaReasoning: Boolean(state.defaultModelConfig.routingConfig?.autoMoaReasoning),
      setRoutingEnabled: state.setRoutingEnabled,
      setAutoMoaReasoning: state.setAutoMoaReasoning,
    })),
  );

  return (
    <SettingsSection
      id={SMART_ROUTING_SECTION_ID}
      title={
        <ModelCardTitle
          icon={<IconRoute className="w-5 h-5 text-emerald-500" />}
          tint="bg-emerald-500/10"
          title={t('smartRouting.title')}
        />
      }
      description={t('smartRouting.description')}
    >
      <div className="space-y-6">
        <label className="flex items-center gap-3 cursor-pointer">
          <button
            type="button"
            role="switch"
            aria-label={t('smartRouting.enable')}
            aria-checked={isRoutingEnabled}
            onClick={() => setRoutingEnabled(!isRoutingEnabled)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              isRoutingEnabled ? 'bg-emerald-500' : 'bg-muted-foreground/30'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                isRoutingEnabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
          <span className="text-sm font-medium text-foreground">{t('smartRouting.enable')}</span>
        </label>

        {isRoutingEnabled && (
          <div className="space-y-6">
            <RoutingTierCard
              icon={<IconZap className="w-4 h-4 text-emerald-500" />}
              title={t('smartRouting.lightModel')}
              description={t('smartRouting.lightModelDescription')}
              primaryLabel={t('smartRouting.selectLightModel')}
              primarySlot="routingLight"
              fallbackSlot="routingLightFallback"
            />

            <div className="p-5 bg-background/50 rounded-xl border border-border/50">
              <div className="flex items-center gap-2 mb-3">
                <IconCpu className="w-4 h-4 text-blue-500" />
                <span className="text-sm font-medium text-foreground">{t('smartRouting.standardModel')}</span>
              </div>
              <p className="text-xs text-muted-foreground">{t('smartRouting.standardModelDescription')}</p>
            </div>

            <RoutingTierCard
              icon={<IconBrain className="w-4 h-4 text-purple-500" />}
              title={t('smartRouting.reasoningModel')}
              description={t('smartRouting.reasoningModelDescription')}
              primaryLabel={t('smartRouting.selectReasoningModel')}
              primarySlot="routingReasoning"
              fallbackSlot="routingReasoningFallback"
            >
              <div className="pt-3 border-t border-border/30">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <span className="text-xs font-medium text-foreground">{t('smartRouting.autoMoaReasoning')}</span>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      {t('smartRouting.autoMoaReasoningDescription')}
                    </p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-label={t('smartRouting.autoMoaReasoning')}
                    aria-checked={autoMoaReasoning}
                    onClick={() => setAutoMoaReasoning(!autoMoaReasoning)}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors flex-shrink-0 ${
                      autoMoaReasoning ? 'bg-purple-500' : 'bg-muted-foreground/30'
                    }`}
                  >
                    <span
                      className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                        autoMoaReasoning ? 'translate-x-4' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>
            </RoutingTierCard>

            <RoutingTierCard
              icon={<IconCode className="w-4 h-4 text-cyan-500" />}
              title={t('smartRouting.codeModel')}
              description={t('smartRouting.codeModelDescription')}
              primaryLabel={t('smartRouting.selectCodeModel')}
              primarySlot="code"
              fallbackSlot="codeFallback"
            />

            <RoutingTierCard
              icon={<IconFileText className="w-4 h-4 text-indigo-500" />}
              title={t('smartRouting.longDocModel')}
              description={t('smartRouting.longDocModelDescription')}
              primaryLabel={t('smartRouting.selectLongDocModel')}
              primarySlot="longDoc"
              fallbackSlot="longDocFallback"
            />
          </div>
        )}
      </div>
    </SettingsSection>
  );
});

SmartRoutingCard.displayName = 'SmartRoutingCard';

export default SmartRoutingCard;
