'use client';

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import {
  IconCpu,
  IconZap,
  IconBrain,
  IconSparkle,
  IconRoute,
  IconCheck,
} from '@/components/features/icons/PremiumIcons';
import { useRouter } from 'next/navigation';

interface ModelOrchestrationPlaybookDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const ModelOrchestrationPlaybookDialog = memo(function ModelOrchestrationPlaybookDialog({
  open,
  onOpenChange,
}: ModelOrchestrationPlaybookDialogProps) {
  const t = useTranslations('modelPlaybook');
  const router = useRouter();

  const handleGoToSettings = (hash?: string) => {
    onOpenChange(false);
    router.push(hash ? `/settings/models#${hash}` : '/settings/models');
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto p-6 sm:p-7">
        <DialogHeader className="space-y-1.5 pb-3 border-b border-border/50">
          <div className="flex items-center gap-2 text-primary font-medium text-xs tracking-wide uppercase">
            <IconSparkle className="w-4 h-4" />
            <span>{t('headerBadge')}</span>
          </div>
          <DialogTitle className="text-xl font-semibold tracking-tight text-foreground">
            {t('dialogTitle')}
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground leading-relaxed">
            {t('dialogSubtitle')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Paradigm 1: Brain & Hands */}
          <div className="rounded-xl border border-border/60 bg-card/60 p-4 space-y-2.5 transition-colors hover:border-primary/30">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-purple-500/10 text-purple-600 dark:text-purple-400">
                  <IconBrain className="w-4 h-4" />
                </div>
                <h3 className="text-sm font-semibold text-foreground">
                  {t('brainHandsTitle')}
                </h3>
              </div>
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-700 dark:text-purple-300">
                {t('brainHandsBadge')}
              </span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t('brainHandsDesc')}
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1 text-xs">
              <div className="flex items-start gap-2 p-2.5 rounded-lg bg-background/60 border border-border/40">
                <IconCheck className="w-3.5 h-3.5 text-emerald-500 mt-0.5 shrink-0" />
                <div>
                  <span className="font-medium text-foreground">{t('brainLabel')}</span>
                  <p className="text-[11px] text-muted-foreground mt-0.5">{t('brainExample')}</p>
                </div>
              </div>
              <div className="flex items-start gap-2 p-2.5 rounded-lg bg-background/60 border border-border/40">
                <IconCheck className="w-3.5 h-3.5 text-emerald-500 mt-0.5 shrink-0" />
                <div>
                  <span className="font-medium text-foreground">{t('handsLabel')}</span>
                  <p className="text-[11px] text-muted-foreground mt-0.5">{t('handsExample')}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Paradigm 2: Dynamic Tier Routing */}
          <div className="rounded-xl border border-border/60 bg-card/60 p-4 space-y-2.5 transition-colors hover:border-primary/30">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                  <IconRoute className="w-4 h-4" />
                </div>
                <h3 className="text-sm font-semibold text-foreground">
                  {t('dynamicRoutingTitle')}
                </h3>
              </div>
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                {t('dynamicRoutingBadge')}
              </span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t('dynamicRoutingDesc')}
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1 text-[11px]">
              <div className="p-2.5 rounded-lg bg-background/60 border border-border/40">
                <span className="font-medium text-foreground block">{t('tierSimpleTitle')}</span>
                <span className="text-muted-foreground mt-0.5 block">{t('tierSimpleDesc')}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-background/60 border border-border/40">
                <span className="font-medium text-foreground block">{t('tierStandardTitle')}</span>
                <span className="text-muted-foreground mt-0.5 block">{t('tierStandardDesc')}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-background/60 border border-border/40">
                <span className="font-medium text-foreground block">{t('tierReasoningTitle')}</span>
                <span className="text-muted-foreground mt-0.5 block">{t('tierReasoningDesc')}</span>
              </div>
            </div>
          </div>

          {/* Paradigm 3: Routing vs MoA Orthogonality */}
          <div className="rounded-xl border border-border/60 bg-card/60 p-4 space-y-2.5 transition-colors hover:border-primary/30">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400">
                  <IconZap className="w-4 h-4" />
                </div>
                <h3 className="text-sm font-semibold text-foreground">
                  {t('moaTitle')}
                </h3>
              </div>
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-700 dark:text-blue-300">
                {t('moaBadge')}
              </span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t('moaDesc')}
            </p>
            <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/15 text-xs text-blue-950 dark:text-blue-200">
              <span className="font-semibold">{t('orthogonalTipTitle')}: </span>
              <span>{t('orthogonalTipDesc')}</span>
            </div>
          </div>

          {/* Paradigm 4: Specialist Slots */}
          <div className="rounded-xl border border-border/60 bg-card/60 p-4 space-y-2 transition-colors hover:border-primary/30">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
                <IconCpu className="w-4 h-4" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">
                {t('specialistsTitle')}
              </h3>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t('specialistsDesc')}
            </p>
          </div>
        </div>

        <div className="pt-3 border-t border-border/50 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-[11px] text-muted-foreground text-center sm:text-left">
            {t('footerNote')}
          </p>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              className="flex-1 sm:flex-initial h-8 text-xs"
            >
              {t('closeBtn')}
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={() => handleGoToSettings('smart-routing')}
              className="flex-1 sm:flex-initial h-8 text-xs font-medium"
            >
              {t('configureBtn')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
});

export default ModelOrchestrationPlaybookDialog;
