'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import {
  ORCHESTRATION_STRATEGIES,
  type OrchestrationStrategy,
} from './modelOrchestrationPlaybookData';
import { Layers, ArrowRight, ShieldCheck, Zap, Cpu, Sparkles } from 'lucide-react';

interface ModelOrchestrationPlaybookDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function ModelOrchestrationPlaybookDialog({
  open,
  onOpenChange,
}: ModelOrchestrationPlaybookDialogProps) {
  const t = useTranslations('settings.modelOrchestrationPlaybook');
  const router = useRouter();

  const handleDeepLink = (linkTarget: OrchestrationStrategy['recommendedSlotLink']) => {
    onOpenChange(false);
    // 优雅深链直达对应设置锚点
    if (linkTarget === 'routing') {
      router.push('/settings/models?focus=routing');
    } else if (linkTarget === 'moa') {
      router.push('/settings/models?focus=moa');
    } else {
      router.push('/settings/models?focus=base');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto p-6 bg-card text-card-foreground border-border shadow-xl">
        <DialogHeader className="space-y-1.5 pb-3 border-b border-border/50 text-left">
          <div className="flex items-center gap-2 text-primary font-semibold text-sm">
            <Layers className="w-4 h-4" />
            <span>{t('headerTag')}</span>
          </div>
          <DialogTitle className="text-xl font-bold tracking-tight">
            {t('modalTitle')}
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground leading-relaxed">
            {t('modalDescription')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-3">
          {ORCHESTRATION_STRATEGIES.map((strategy) => (
            <div
              key={strategy.id}
              className="group relative rounded-xl border border-border/70 bg-secondary/20 p-4 transition-all duration-200 hover:border-primary/40 hover:bg-secondary/40 space-y-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-primary/10 text-primary border border-primary/20">
                    <Sparkles className="w-3 h-3" />
                    {t(strategy.badgeKey)}
                  </span>
                  <h3 className="font-semibold text-sm text-foreground">
                    {t(strategy.titleKey)}
                  </h3>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleDeepLink(strategy.recommendedSlotLink)}
                  className="h-7 text-xs px-2.5 gap-1.5 group-hover:border-primary group-hover:text-primary transition-colors"
                >
                  <span>{t('applyOrConfigure')}</span>
                  <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
                </Button>
              </div>

              <p className="text-xs text-muted-foreground leading-relaxed">
                {t(strategy.descriptionKey)}
              </p>

              {/* 槽位分工 */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs pt-1">
                <div className="rounded-lg bg-background/60 p-2.5 border border-border/40 space-y-1">
                  <div className="flex items-center gap-1.5 font-medium text-foreground">
                    <Cpu className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                    <span>{t(strategy.slots.brainRoleKey)}</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-normal">
                    {t(strategy.slots.brainDescKey)}
                  </p>
                </div>
                <div className="rounded-lg bg-background/60 p-2.5 border border-border/40 space-y-1">
                  <div className="flex items-center gap-1.5 font-medium text-foreground">
                    <Zap className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                    <span>{t(strategy.slots.handsRoleKey)}</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-normal">
                    {t(strategy.slots.handsDescKey)}
                  </p>
                </div>
              </div>

              {/* Token 经济学优势 */}
              <div className="flex items-center gap-1.5 text-[11px] text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2.5 py-1.5 rounded-lg border border-emerald-500/20">
                <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
                <span>{t(strategy.tokenEconomicsKey)}</span>
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
