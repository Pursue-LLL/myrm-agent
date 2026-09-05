'use client';

import React from 'react';
import { AlertCircle, CheckCircle2, ShieldAlert } from 'lucide-react';

export interface TaskBudgetPillProps {
  totalTokens: number;
  hardLimit?: number;
  isPaused?: boolean;
  onExtendBudget?: (additionalTokens: number) => void;
  className?: string;
}

export const TaskBudgetPill: React.FC<TaskBudgetPillProps> = ({
  totalTokens,
  hardLimit,
  isPaused = false,
  onExtendBudget,
  className = '',
}) => {
  if (!hardLimit || hardLimit <= 0) {
    return null;
  }

  const ratio = Math.min(1, totalTokens / hardLimit);
  const percent = Math.round(ratio * 100);
  const isSoftWarning = ratio >= 0.8 && ratio < 1.0;
  const isBreached = ratio >= 1.0 || isPaused;

  return (
    <div
      data-testid="task-budget-pill"
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
        isBreached
          ? 'border-destructive/40 bg-destructive/10 text-destructive'
          : isSoftWarning
            ? 'border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400'
            : 'border-border bg-muted/50 text-muted-foreground'
      } ${className}`}
    >
      {isBreached ? (
        <ShieldAlert className="h-3.5 w-3.5 shrink-0" data-testid="icon-breached" />
      ) : isSoftWarning ? (
        <AlertCircle className="h-3.5 w-3.5 shrink-0" data-testid="icon-warning" />
      ) : (
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0" data-testid="icon-normal" />
      )}

      <span>
        {totalTokens.toLocaleString()} / {hardLimit.toLocaleString()} ({percent}%)
      </span>

      {isBreached && onExtendBudget && (
        <button
          type="button"
          onClick={() => onExtendBudget(20000)}
          data-testid="btn-extend-budget"
          className="ml-1 rounded bg-destructive/20 px-1.5 py-0.5 text-[11px] font-semibold text-destructive hover:bg-destructive/30 transition-colors"
        >
          放行+20k
        </button>
      )}
    </div>
  );
};
