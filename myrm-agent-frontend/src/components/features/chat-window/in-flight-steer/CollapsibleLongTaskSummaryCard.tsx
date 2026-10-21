/**
 * [INPUT] CollapsibleLongTaskSummary entity from store or props
 * [OUTPUT] CollapsibleLongTaskSummaryCard (Progress bar and collapsible context summary for long-running agent workflows)
 * [POS] Features -> Chat Window -> In-Flight Steer -> CollapsibleSummaryCard
 */

'use client';

import React from 'react';
import {
  Layers,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  Circle,
  Bot,
  Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { CollapsibleLongTaskSummary } from './inFlightSteerTypes';
import { useInFlightSteerStore } from './useInFlightSteerStore';

export interface CollapsibleLongTaskSummaryCardProps {
  summary: CollapsibleLongTaskSummary;
  className?: string;
}

export const CollapsibleLongTaskSummaryCard: React.FC<CollapsibleLongTaskSummaryCardProps> = ({
  summary,
  className,
}) => {
  const { toggleSummaryCollapse } = useInFlightSteerStore();

  const progressPercent =
    summary.totalSteps > 0
      ? Math.min(100, Math.round((summary.completedSteps / summary.totalSteps) * 100))
      : 0;

  return (
    <div
      className={cn(
        'w-full my-3 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white/90 dark:bg-neutral-850/90 shadow-sm overflow-hidden transition-all',
        className,
      )}
    >
      {/* Header / Clickable Toggle */}
      <button
        type="button"
        onClick={() => toggleSummaryCollapse(summary.id)}
        aria-expanded={!summary.isCollapsed}
        aria-label={summary.isCollapsed ? `展开任务详情: ${summary.goalTitle}` : `折叠任务详情: ${summary.goalTitle}`}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
      >
        <div className="flex items-center gap-3 flex-1 min-w-0 mr-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 shrink-0">
            <Layers size={17} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h4 className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                {summary.goalTitle}
              </h4>
              <span className="px-1.5 py-0.2 text-[10px] font-medium rounded-full bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 shrink-0">
                {summary.completedSteps}/{summary.totalSteps} 步骤 ({progressPercent}%)
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5 text-[11px] text-neutral-500 dark:text-neutral-400">
              <span className="inline-flex items-center gap-1">
                <Bot size={11} className="text-neutral-400" />
                <span>当前负责: {summary.currentActiveAgentName}</span>
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-neutral-400 font-medium max-sm:hidden">
            {summary.isCollapsed ? '展开详情' : '折叠摘要'}
          </span>
          <div className="p-1 rounded text-neutral-400">
            {summary.isCollapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
          </div>
        </div>
      </button>

      {/* Progress Bar */}
      <div className="w-full h-1 bg-neutral-100 dark:bg-neutral-800 overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-indigo-500 to-emerald-500 transition-all duration-300 ease-out"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Expanded Content Area */}
      {!summary.isCollapsed ? (
        <div className="p-4 pt-3 border-t border-neutral-100 dark:border-neutral-800 bg-neutral-50/40 dark:bg-neutral-900/40 animate-in fade-in slide-in-from-top-1 duration-150">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
            <Sparkles size={13} className="text-amber-500" />
            <span>阶段性产物与关键发现 ({summary.keyFindings.length})</span>
          </div>

          {summary.keyFindings.length === 0 ? (
            <p className="text-xs text-neutral-400 italic">暂无阶段性总结产物...</p>
          ) : (
            <div className="space-y-1.5">
              {summary.keyFindings.map((finding, idx) => (
                <div
                  key={`${summary.id}-finding-${idx}`}
                  className="flex items-start gap-2 p-2 rounded-lg bg-white dark:bg-neutral-800 border border-neutral-200/70 dark:border-neutral-700/70 text-xs text-neutral-800 dark:text-neutral-200"
                >
                  <CheckCircle2 size={13} className="text-emerald-500 mt-0.5 shrink-0" />
                  <span className="leading-relaxed">{finding}</span>
                </div>
              ))}
            </div>
          )}

          <div className="mt-3 pt-2.5 flex items-center justify-between text-[10px] text-neutral-400 dark:text-neutral-500 border-t border-neutral-200/50 dark:border-neutral-800">
            <span>多智能体协作工作流 · 实时脉冲归约</span>
            <span>更新于 {new Date(summary.updatedAt).toLocaleTimeString()}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
};

CollapsibleLongTaskSummaryCard.displayName = 'CollapsibleLongTaskSummaryCard';
