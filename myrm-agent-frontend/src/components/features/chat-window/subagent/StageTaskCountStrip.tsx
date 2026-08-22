'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle2, CircleDashed, Clock, Loader2, XCircle } from 'lucide-react';
import { type StageProgressItem, type StageTaskCountSummary } from '@/lib/utils/stageTaskCount';

interface StageTaskCountStripProps {
  summary: StageTaskCountSummary;
  className?: string;
}

export const StageTaskCountStrip: React.FC<StageTaskCountStripProps> = ({ summary, className = '' }) => {
  const t = useTranslations('subagentDashboard');

  if (!summary || summary.stages.length === 0) {
    return null;
  }

  return (
    <div
      data-testid="stage-task-count-strip"
      className={`flex items-center gap-2 flex-wrap py-1.5 px-2.5 rounded-lg bg-muted/40 border border-border/50 text-xs ${className}`}
    >
      <div className="flex items-center gap-1 font-medium text-muted-foreground text-[11px] shrink-0">
        <Clock className="w-3.5 h-3.5 text-primary/70" />
        <span>{t('stagesProgress') || 'Workflow Stages'}:</span>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {summary.stages.map((stage: StageProgressItem) => {
          const isDone = stage.isComplete;
          const isRunning = stage.running > 0;
          const isBlocked = stage.isBlocked;

          return (
            <div
              key={stage.id}
              data-testid={`stage-item-${stage.category}`}
              className={`flex items-center gap-1.5 px-2 py-0.5 rounded-md border text-[11px] transition-colors ${
                isDone
                  ? 'bg-green-50/80 text-green-700 dark:bg-green-950/30 dark:text-green-400 border-green-200 dark:border-green-800/60'
                  : isRunning
                    ? 'bg-blue-50/80 text-blue-700 dark:bg-blue-950/30 dark:text-blue-400 border-blue-200 dark:border-blue-800/60 animate-pulse'
                    : isBlocked
                      ? 'bg-amber-50/80 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400 border-amber-200 dark:border-amber-800/60'
                      : 'bg-background/80 text-muted-foreground border-border/60'
              }`}
            >
              {isDone ? (
                <CheckCircle2 className="w-3 h-3 text-green-600 dark:text-green-400 shrink-0" />
              ) : isRunning ? (
                <Loader2 className="w-3 h-3 text-blue-600 dark:text-blue-400 animate-spin shrink-0" />
              ) : stage.failed > 0 ? (
                <XCircle className="w-3 h-3 text-red-600 dark:text-red-400 shrink-0" />
              ) : (
                <CircleDashed className="w-3 h-3 text-muted-foreground/60 shrink-0" />
              )}

              <span className="font-semibold">{stage.name}</span>
              <span className="font-mono text-[10px]">
                {stage.completed}/{stage.total}
              </span>

              {stage.waitingOnStage && (
                <span className="text-[10px] text-amber-600 dark:text-amber-400 font-normal ml-0.5 opacity-90">
                  (waiting on {stage.waitingOnStage})
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default StageTaskCountStrip;
