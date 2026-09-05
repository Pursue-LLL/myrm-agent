'use client';

/**
 * [INPUT]
 * - useProviderStore: setRoutingEnabled, defaultModelConfig
 * - useTranslations: modelPlaybook 国际化翻译
 * - useRouter: 前往设置页导航
 *
 * [OUTPUT]
 * - ModelOrchestrationPlaybookModal: 响应式模型编排与选型心法指南弹窗/抽屉
 *
 * [POS]
 * components/features/model-orchestration/ModelOrchestrationPlaybookModal.tsx
 * 独立解耦的发现层与认知赋能模态，用于 EmptyChat 与 DefaultModelSection。
 */

import { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import useProviderStore from '@/store/useProviderStore';
import { toast } from 'sonner';
import {
  IconBrain,
  IconZap,
  IconRoute,
  IconSparkles,
  IconShield,
  IconCheck,
  IconExternalLink,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';

interface ModelOrchestrationPlaybookModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  className?: string;
}

export const ModelOrchestrationPlaybookModal = memo(function ModelOrchestrationPlaybookModal({
  open,
  onOpenChange,
  className,
}: ModelOrchestrationPlaybookModalProps) {
  const t = useTranslations('modelPlaybook');
  const router = useRouter();

  const isRoutingEnabled = useProviderStore((state) => state.defaultModelConfig.smartRouting?.enabled ?? false);
  const setRoutingEnabled = useProviderStore((state) => state.setRoutingEnabled);

  const handleEnableRouting = useCallback(() => {
    setRoutingEnabled(true);
    toast.success(t('actions.routingEnabledSuccess'));
  }, [setRoutingEnabled, t]);

  const handleGoToSettings = useCallback(
    (hash?: string) => {
      onOpenChange(false);
      router.push(`/settings?tab=models${hash ? `#${hash}` : ''}`);
    },
    [onOpenChange, router],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          'w-full sm:max-w-3xl max-h-[90vh] overflow-y-auto p-6 sm:p-7 bg-background/95 backdrop-blur-xl border border-border/70 rounded-2xl shadow-2xl',
          className,
        )}
      >
        <DialogHeader className="pb-4 border-b border-border/50 text-left">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-primary/10 border border-primary/20 text-primary">
              <IconSparkles className="w-5 h-5" />
            </div>
            <div>
              <DialogTitle className="text-xl font-bold tracking-tight text-foreground">
                {t('title')}
              </DialogTitle>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                {t('subtitle')}
              </p>
            </div>
          </div>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-4">
          {/* Quadrant 1: Brain vs Hands */}
          <div className="p-4 rounded-xl border border-border/60 bg-card/60 flex flex-col justify-between hover:border-primary/40 transition-colors">
            <div>
              <div className="flex items-center justify-between mb-2.5">
                <div className="flex items-center gap-2 text-indigo-500 font-semibold text-sm">
                  <div className="p-1.5 rounded-lg bg-indigo-500/10">
                    <IconBrain className="w-4 h-4" />
                  </div>
                  <span>{t('brainHands.title')}</span>
                </div>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
                  {t('brainHands.tag')}
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                {t('brainHands.description')}
              </p>
              <div className="space-y-1.5 bg-muted/30 p-2.5 rounded-lg border border-border/40 text-[11px]">
                <div className="flex items-start gap-1.5 text-foreground/90">
                  <span className="font-semibold text-indigo-600 dark:text-indigo-400 shrink-0">Brain:</span>
                  <span className="text-muted-foreground">{t('brainHands.brainTip')}</span>
                </div>
                <div className="flex items-start gap-1.5 text-foreground/90">
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400 shrink-0">Hands:</span>
                  <span className="text-muted-foreground">{t('brainHands.handsTip')}</span>
                </div>
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-border/40 flex justify-end">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleGoToSettings('base-model')}
                className="text-xs h-8 gap-1.5 hover:bg-indigo-500/10 hover:text-indigo-600 hover:border-indigo-500/30"
              >
                <span>{t('actions.configureSlots')}</span>
                <IconExternalLink className="w-3 h-3" />
              </Button>
            </div>
          </div>

          {/* Quadrant 2: Routing vs MoA Orthogonality */}
          <div className="p-4 rounded-xl border border-border/60 bg-card/60 flex flex-col justify-between hover:border-emerald-500/40 transition-colors">
            <div>
              <div className="flex items-center justify-between mb-2.5">
                <div className="flex items-center gap-2 text-emerald-500 font-semibold text-sm">
                  <div className="p-1.5 rounded-lg bg-emerald-500/10">
                    <IconRoute className="w-4 h-4" />
                  </div>
                  <span>{t('routingMoa.title')}</span>
                </div>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                  {t('routingMoa.tag')}
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                {t('routingMoa.description')}
              </p>
              <div className="space-y-1.5 bg-muted/30 p-2.5 rounded-lg border border-border/40 text-[11px]">
                <div className="flex items-start gap-1.5 text-foreground/90">
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400 shrink-0">Routing:</span>
                  <span className="text-muted-foreground">{t('routingMoa.routingTip')}</span>
                </div>
                <div className="flex items-start gap-1.5 text-foreground/90">
                  <span className="font-semibold text-primary shrink-0">MoA:</span>
                  <span className="text-muted-foreground">{t('routingMoa.moaTip')}</span>
                </div>
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-border/40 flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground">
                {isRoutingEnabled ? t('routingMoa.routingActive') : t('routingMoa.routingInactive')}
              </span>
              {isRoutingEnabled ? (
                <div className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                  <IconCheck className="w-3.5 h-3.5" />
                  <span>{t('actions.enabled')}</span>
                </div>
              ) : (
                <Button
                  size="sm"
                  onClick={handleEnableRouting}
                  className="text-xs h-8 gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white"
                >
                  <IconZap className="w-3 h-3" />
                  <span>{t('actions.enableSmartRouting')}</span>
                </Button>
              )}
            </div>
          </div>

          {/* Quadrant 3: Cheap Eyes & Vision Routing */}
          <div className="p-4 rounded-xl border border-border/60 bg-card/60 flex flex-col justify-between hover:border-purple-500/40 transition-colors">
            <div>
              <div className="flex items-center justify-between mb-2.5">
                <div className="flex items-center gap-2 text-purple-500 font-semibold text-sm">
                  <div className="p-1.5 rounded-lg bg-purple-500/10">
                    <IconSparkles className="w-4 h-4" />
                  </div>
                  <span>{t('cheapEyes.title')}</span>
                </div>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                  {t('cheapEyes.tag')}
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                {t('cheapEyes.description')}
              </p>
              <div className="bg-muted/30 p-2.5 rounded-lg border border-border/40 text-[11px] text-muted-foreground">
                {t('cheapEyes.tip')}
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-border/40 flex justify-end">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleGoToSettings('vision-model')}
                className="text-xs h-8 gap-1.5 hover:bg-purple-500/10 hover:text-purple-600 hover:border-purple-500/30"
              >
                <span>{t('actions.configureVision')}</span>
                <IconExternalLink className="w-3 h-3" />
              </Button>
            </div>
          </div>

          {/* Quadrant 4: Honest Quota & Subscription Harmony */}
          <div className="p-4 rounded-xl border border-border/60 bg-card/60 flex flex-col justify-between hover:border-amber-500/40 transition-colors">
            <div>
              <div className="flex items-center justify-between mb-2.5">
                <div className="flex items-center gap-2 text-amber-500 font-semibold text-sm">
                  <div className="p-1.5 rounded-lg bg-amber-500/10">
                    <IconShield className="w-4 h-4" />
                  </div>
                  <span>{t('honestQuota.title')}</span>
                </div>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                  {t('honestQuota.tag')}
                </span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                {t('honestQuota.description')}
              </p>
              <div className="bg-muted/30 p-2.5 rounded-lg border border-border/40 text-[11px] text-muted-foreground">
                {t('honestQuota.tip')}
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-border/40 flex justify-end">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleGoToSettings('subscriptions')}
                className="text-xs h-8 gap-1.5 hover:bg-amber-500/10 hover:text-amber-600 hover:border-amber-500/30"
              >
                <span>{t('actions.viewSubscriptions')}</span>
                <IconExternalLink className="w-3 h-3" />
              </Button>
            </div>
          </div>
        </div>

        <div className="pt-3 border-t border-border/50 flex items-center justify-between text-xs text-muted-foreground">
          <span>{t('footerNote')}</span>
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)} className="text-xs h-8">
            {t('actions.close')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
});
