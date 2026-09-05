'use client';

import React, { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import {
  IconRoute,
  IconSparkle,
  IconChevronDown,
  IconChevronUp,
  IconBrain,
  IconZap,
  IconCpu,
} from '@/components/features/icons/PremiumIcons';
import { ModelOrchestrationPlaybookDialog } from '@/components/features/chat-window/playbook';

export const ModelOrchestrationPlaybookCard = memo(function ModelOrchestrationPlaybookCard() {
  const t = useTranslations('modelPlaybook');
  const [isExpanded, setIsExpanded] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <>
      <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-4 sm:p-5 transition-all mb-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start sm:items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5 sm:mt-0">
              <IconSparkle className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-foreground">
                  {t('cardTitle')}
                </span>
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-800 dark:text-emerald-300">
                  {t('cardBadge')}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {t('cardSubtitle')}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDialogOpen(true)}
              className="h-8 text-xs font-medium border-emerald-500/30 bg-background/60 hover:bg-emerald-500/10"
            >
              {t('viewFullPlaybook')}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded((prev) => !prev)}
              className="h-8 px-2 text-xs text-muted-foreground hover:text-foreground"
              aria-label={isExpanded ? t('collapse') : t('expand')}
            >
              {isExpanded ? (
                <IconChevronUp className="w-4 h-4" />
              ) : (
                <IconChevronDown className="w-4 h-4" />
              )}
            </Button>
          </div>
        </div>

        {isExpanded && (
          <div className="mt-4 pt-3.5 border-t border-emerald-500/15 grid grid-cols-1 sm:grid-cols-3 gap-3 animate-in fade-in-50 duration-200">
            <div className="p-3 rounded-lg bg-background/50 border border-border/40 space-y-1">
              <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <IconBrain className="w-3.5 h-3.5 text-purple-500" />
                <span>{t('miniBrainHandsTitle')}</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {t('miniBrainHandsDesc')}
              </p>
            </div>

            <div className="p-3 rounded-lg bg-background/50 border border-border/40 space-y-1">
              <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <IconRoute className="w-3.5 h-3.5 text-emerald-500" />
                <span>{t('miniDynamicRoutingTitle')}</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {t('miniDynamicRoutingDesc')}
              </p>
            </div>

            <div className="p-3 rounded-lg bg-background/50 border border-border/40 space-y-1">
              <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <IconZap className="w-3.5 h-3.5 text-blue-500" />
                <span>{t('miniMoaTitle')}</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {t('miniMoaDesc')}
              </p>
            </div>
          </div>
        )}
      </div>

      <ModelOrchestrationPlaybookDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </>
  );
});

export default ModelOrchestrationPlaybookCard;
