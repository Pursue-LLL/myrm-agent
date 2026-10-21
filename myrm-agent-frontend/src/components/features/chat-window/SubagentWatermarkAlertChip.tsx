'use client';

import React, { useState } from 'react';
import { AlertTriangle, PlusCircle, BellRing, X } from 'lucide-react';

export interface SubagentWatermarkAlertChipProps {
  subagentId: string;
  subagentName?: string;
  currentTurn: number;
  maxTurns: number;
  thresholdRatio?: number;
  onDismiss?: (subagentId: string) => void;
  onExpandBudget?: (subagentId: string) => void;
  onNotifyParent?: (subagentId: string, currentTurn: number, maxTurns: number) => void;
  className?: string;
}

export const SubagentWatermarkAlertChip: React.FC<SubagentWatermarkAlertChipProps> = ({
  subagentId,
  subagentName = 'Subagent',
  currentTurn,
  maxTurns,
  thresholdRatio = 0.8,
  onDismiss,
  onExpandBudget,
  onNotifyParent,
  className = '',
}) => {
  const [isDismissed, setIsDismissed] = useState(false);
  const [isNotified, setIsNotified] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  if (isDismissed || maxTurns <= 0) {
    return null;
  }

  const usageRatio = Math.min(1.0, Math.max(0.0, currentTurn / maxTurns));
  if (usageRatio < thresholdRatio) {
    return null;
  }

  const percentage = (usageRatio * 100).toFixed(1);
  const turnsRemaining = Math.max(0, maxTurns - currentTurn);

  const handleDismiss = () => {
    setIsDismissed(true);
    onDismiss?.(subagentId);
  };

  const handleExpand = () => {
    setIsExpanded(true);
    onExpandBudget?.(subagentId);
  };

  const handleNotify = () => {
    setIsNotified(true);
    onNotifyParent?.(subagentId, currentTurn, maxTurns);
  };

  return (
    <div
      data-testid="subagent-watermark-alert"
      className={`flex flex-col gap-2 p-3 rounded-lg border border-amber-300 dark:border-amber-700/60 bg-amber-50/90 dark:bg-amber-950/40 text-amber-950 dark:text-amber-100 shadow-sm transition-all duration-200 text-xs ${className}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-medium">
          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 animate-pulse" />
          <span className="font-semibold text-amber-900 dark:text-amber-200">
            [80% 配额水位预警]
          </span>
          <span className="truncate max-w-[140px] text-zinc-700 dark:text-zinc-300">
            {subagentName}
          </span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-200/70 dark:bg-amber-900/60 text-amber-800 dark:text-amber-300">
            {percentage}%
          </span>
        </div>

        <button
          type="button"
          data-testid="dismiss-alert-button"
          onClick={handleDismiss}
          className="p-1 rounded hover:bg-amber-200/60 dark:hover:bg-amber-800/50 text-amber-700 dark:text-amber-300 transition-colors"
          title="忽略预警"
          aria-label="忽略预警"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between text-[11px] text-amber-800 dark:text-amber-300">
          <span>
            已执行 {currentTurn} / {maxTurns} 轮
          </span>
          <span>剩余 {turnsRemaining} 轮达到上限</span>
        </div>
        <div
          data-testid="watermark-progress-bar"
          className="w-full h-1.5 bg-amber-200/80 dark:bg-amber-900/60 rounded-full overflow-hidden"
        >
          <div
            className="h-full bg-gradient-to-r from-amber-500 to-rose-500 transition-all duration-300 rounded-full"
            style={{ width: `${Math.min(100, Math.max(0, usageRatio * 100))}%` }}
          />
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 pt-1 border-t border-amber-200/50 dark:border-amber-800/40">
        <button
          type="button"
          data-testid="notify-parent-button"
          disabled={isNotified}
          onClick={handleNotify}
          className={`inline-flex items-center gap-1 px-2 py-1 rounded font-medium text-[11px] transition-colors ${
            isNotified
              ? 'bg-zinc-200 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-500 cursor-not-allowed'
              : 'bg-amber-100 hover:bg-amber-200/80 text-amber-900 dark:bg-amber-900/50 dark:hover:bg-amber-800/60 dark:text-amber-200'
          }`}
        >
          <BellRing className="w-3 h-3" />
          {isNotified ? '已通知父智能体' : '通知父智能体'}
        </button>

        <button
          type="button"
          data-testid="expand-budget-button"
          disabled={isExpanded}
          onClick={handleExpand}
          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded font-medium text-[11px] transition-colors ${
            isExpanded
              ? 'bg-zinc-200 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-500 cursor-not-allowed'
              : 'bg-amber-600 hover:bg-amber-700 text-white dark:bg-amber-500 dark:hover:bg-amber-600'
          }`}
        >
          <PlusCircle className="w-3 h-3" />
          {isExpanded ? '已扩容配额' : '扩容 +100 轮'}
        </button>
      </div>
    </div>
  );
};

export default SubagentWatermarkAlertChip;
