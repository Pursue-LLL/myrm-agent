'use client';

/**
 * [INPUT]
 * - ./types::LaborAccelerationSummary, LaborEquivalencyItem (POS: 效能数据契约)
 * - lucide-react::Rocket, Clock, Copy, Check, ChevronDown, ChevronUp, Sparkles, TrendingUp (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - TaskAccelerationBadge: 单任务白领劳务效能加速与工时挽回战报徽章
 *
 * [POS]
 * src/components/features/system-monitor/TaskAccelerationBadge.tsx — 单任务效能加速倍率与工时战报徽章。
 */

import React, { useState } from 'react';
import {
  Rocket,
  Clock,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import type { LaborAccelerationSummary } from './types';

interface TaskAccelerationBadgeProps {
  summary: LaborAccelerationSummary;
  className?: string;
  showDetailsToggle?: boolean;
}

export const TaskAccelerationBadge: React.FC<TaskAccelerationBadgeProps> = ({
  summary,
  className = '',
  showDetailsToggle = true,
}) => {
  const [copied, setCopied] = useState<boolean>(false);
  const [isExpanded, setIsExpanded] = useState<boolean>(false);

  const reportText = `🚀 AI 效能加速: ${summary.acceleration_factor.toFixed(1)}× | 挽回工时: ~${summary.total_hours_saved.toFixed(2)} 小时 | 本次耗时: ${summary.task_elapsed_seconds.toFixed(0)}s | 商业价值: ~$${summary.estimated_saved_value_usd.toFixed(2)}`;

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(reportText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // 剪贴板异常回退
    }
  };

  return (
    <div className={`inline-flex flex-col text-xs ${className}`}>
      {/* 核心徽章条 */}
      <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-foreground shadow-sm">
        <span className="flex items-center gap-1 font-semibold text-primary">
          <Rocket className="w-3.5 h-3.5 text-primary animate-pulse" />
          <span>加速 {summary.acceleration_factor.toFixed(1)}×</span>
        </span>

        <span className="w-1 h-1 rounded-full bg-border" />

        <span className="flex items-center gap-1 text-muted-foreground">
          <Clock className="w-3 h-3 text-emerald-500" />
          <span>挽回 ~{summary.total_hours_saved.toFixed(2)}h</span>
        </span>

        <span className="w-1 h-1 rounded-full bg-border" />

        <span className="text-[11px] font-mono text-muted-foreground">
          用时 {summary.task_elapsed_seconds.toFixed(0)}s
        </span>

        {/* 复制战报按钮 */}
        <button
          type="button"
          onClick={handleCopy}
          aria-label="复制生产力战报"
          title="复制到剪贴板，用于日报或团队汇报"
          className="ml-1 p-1 rounded-full hover:bg-primary/20 text-primary transition-colors"
        >
          {copied ? (
            <Check className="w-3.5 h-3.5 text-emerald-500" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
        </button>

        {/* 展开明细控制 */}
        {showDetailsToggle && summary.breakdown.length > 0 && (
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            aria-label={isExpanded ? '收起工时置换明细' : '展开工时置换明细'}
            className="p-1 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          >
            {isExpanded ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        )}
      </div>

      {/* 展开的工时置换明细卡片 */}
      {isExpanded && summary.breakdown.length > 0 && (
        <div className="mt-2 p-3 rounded-lg border border-border bg-card shadow-lg space-y-2 w-full max-w-sm">
          <div className="flex items-center justify-between pb-1.5 border-b border-border/60">
            <span className="text-[11px] font-medium text-foreground flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-primary" />
              人工劳务置换等效矩阵
            </span>
            <span className="text-[10px] text-muted-foreground font-mono">
              ROI: {summary.roi_ratio.toFixed(0)}×
            </span>
          </div>

          <div className="space-y-1.5">
            {summary.breakdown.map((item, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between text-[11px] py-0.5 text-muted-foreground"
              >
                <span className="truncate pr-2">{item.label}</span>
                <span className="font-mono shrink-0 text-foreground">
                  {item.count}次 ≈ {item.total_hours_saved.toFixed(2)}h
                </span>
              </div>
            ))}
          </div>

          <div className="pt-1.5 border-t border-border/60 flex items-center justify-between text-[11px]">
            <span className="text-muted-foreground flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-emerald-500" />
              商业工时价值 ($35/h)
            </span>
            <span className="font-mono font-semibold text-emerald-600 dark:text-emerald-400">
              +${summary.estimated_saved_value_usd.toFixed(2)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
