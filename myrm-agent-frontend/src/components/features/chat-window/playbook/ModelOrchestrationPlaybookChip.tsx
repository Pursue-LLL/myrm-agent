'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: 多语言国际化)
 * - lucide-react::Sparkles, ArrowRight, X, Brain (POS: 现代矢量图标)
 * - ./ModelOrchestrationPlaybookDialog (POS: 编排最佳实践看板弹窗)
 *
 * [OUTPUT]
 * - ModelOrchestrationPlaybookChip: EmptyChat 首屏模型编排最佳实践发现胶囊
 *
 * [POS]
 * 空聊天界面模型编排心智发现层。引导用户理解 Brain/Hands 双模协同与 Agent 4x Token 经济学，
 * 并在点击时展开全屏交互式编排看板。
 */

import React, { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Sparkles, ArrowRight, X, Brain } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { ModelOrchestrationPlaybookDialog } from './ModelOrchestrationPlaybookDialog';

interface ModelOrchestrationPlaybookChipProps {
  className?: string;
}

const DISMISS_KEY = 'myrm_model_playbook_chip_dismissed';

export const ModelOrchestrationPlaybookChip = memo(function ModelOrchestrationPlaybookChip({
  className,
}: ModelOrchestrationPlaybookChipProps) {
  const t = useTranslations('chat.modelPlaybook');
  const [dismissed, setDismissed] = useState<boolean>(true);
  const [dialogOpen, setDialogOpen] = useState<boolean>(false);

  useEffect(() => {
    try {
      const isDismissed = sessionStorage.getItem(DISMISS_KEY) === 'true';
      setDismissed(isDismissed);
    } catch {
      setDismissed(false);
    }
  }, []);

  const handleOpen = useCallback(() => {
    setDialogOpen(true);
  }, []);

  const handleDismiss = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      sessionStorage.setItem(DISMISS_KEY, 'true');
    } catch {
      // Ignore sessionStorage failure
    }
    setDismissed(true);
  }, []);

  if (dismissed) {
    return (
      <ModelOrchestrationPlaybookDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    );
  }

  return (
    <>
      <div
        data-testid="model-orchestration-playbook-chip"
        onClick={handleOpen}
        className={cn(
          'group relative w-full flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl cursor-pointer select-none',
          'bg-gradient-to-r from-purple-500/5 via-indigo-500/5 to-sky-500/5 dark:from-purple-950/20 dark:via-indigo-950/20 dark:to-sky-950/20',
          'border border-purple-500/20 dark:border-purple-500/15 hover:border-purple-500/35 dark:hover:border-purple-500/30',
          'shadow-xs hover:shadow-sm transition-all duration-200',
          className,
        )}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-purple-500/10 text-purple-600 dark:text-purple-400 shrink-0 group-hover:scale-105 transition-transform">
            <Brain className="w-4 h-4" />
          </div>
          <div className="flex flex-col min-w-0 text-left">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-neutral-800 dark:text-neutral-200 truncate">
                {t('chipTitle')}
              </span>
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded-md bg-purple-500/10 text-purple-700 dark:text-purple-300 border border-purple-500/20 shrink-0">
                <Sparkles className="w-2.5 h-2.5" />
                {t('chipBadge')}
              </span>
            </div>
            <span className="text-[11px] text-neutral-500 dark:text-neutral-400 truncate">
              {t('chipSubtitle')}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="hidden sm:inline-flex items-center gap-1 text-xs font-medium text-purple-600 dark:text-purple-400 group-hover:text-purple-700 dark:group-hover:text-purple-300 transition-colors">
            {t('chipAction')}
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </span>
          <button
            type="button"
            onClick={handleDismiss}
            className="p-1 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 hover:bg-neutral-200/50 dark:hover:bg-neutral-800/50 transition-colors"
            aria-label={t('dismiss')}
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <ModelOrchestrationPlaybookDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </>
  );
});

ModelOrchestrationPlaybookChip.displayName = 'ModelOrchestrationPlaybookChip';
