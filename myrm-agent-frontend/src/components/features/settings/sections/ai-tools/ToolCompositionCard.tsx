'use client';

/**
 * [INPUT]
 * - services/statistics::ToolStabilityDaily (POS: 日维度工具稳定性数据契约)
 * - lucide-react::PieChart, ChevronDown, ChevronRight, Clock, Hash, AlertCircle (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - ToolCompositionCard: 工具周期调用量与累计耗时构成视图组件
 * - computeToolComposition: 纯确定性周期构成聚合计算纯函数
 *
 * [POS]
 * src/components/features/settings/sections/ai-tools/ToolCompositionCard.tsx — 工具构成与耗时占比分析卡。
 */

import React, { useState, useMemo } from 'react';
import { PieChart, ChevronDown, ChevronRight, Clock, Hash, Info } from 'lucide-react';
import type { ToolStabilityDaily } from '@/services/statistics';

export interface ToolCompositionItem {
  tool_name: string;
  calls: number;
  calls_percent: number;
  duration_ms: number;
  duration_percent: number;
}

export interface ToolCompositionSummary {
  totalCalls: number;
  totalDurationMs: number;
  topTools: ToolCompositionItem[];
  otherTools: ToolCompositionItem[];
  otherCallsTotal: number;
  otherCallsPercent: number;
  otherDurationTotal: number;
  otherDurationPercent: number;
}

/**
 * 纯确定性聚合计算工具周期构成比率。
 * 遵循 Hermes insights 原则：前 3 项高亮展示，其余折叠收纳。
 */
export function computeToolComposition(
  dailyRecords: ToolStabilityDaily[],
): ToolCompositionSummary {
  if (!dailyRecords || dailyRecords.length === 0) {
    return {
      totalCalls: 0,
      totalDurationMs: 0,
      topTools: [],
      otherTools: [],
      otherCallsTotal: 0,
      otherCallsPercent: 0,
      otherDurationTotal: 0,
      otherDurationPercent: 0,
    };
  }

  // 1. 按工具名聚合总调用数与累计耗时 (total_calls * avg_duration_ms)
  const map = new Map<string, { calls: number; duration_ms: number }>();
  let totalCalls = 0;
  let totalDurationMs = 0;

  for (const record of dailyRecords) {
    const existing = map.get(record.tool_name) || { calls: 0, duration_ms: 0 };
    const recordDuration = record.total_calls * record.avg_duration_ms;
    existing.calls += record.total_calls;
    existing.duration_ms += recordDuration;
    map.set(record.tool_name, existing);

    totalCalls += record.total_calls;
    totalDurationMs += recordDuration;
  }

  if (totalCalls === 0) {
    return {
      totalCalls: 0,
      totalDurationMs: 0,
      topTools: [],
      otherTools: [],
      otherCallsTotal: 0,
      otherCallsPercent: 0,
      otherDurationTotal: 0,
      otherDurationPercent: 0,
    };
  }

  // 2. 转换为数组并计算初版百分比
  const items: ToolCompositionItem[] = [];
  for (const [tool_name, data] of map.entries()) {
    const calls_percent = Number(((data.calls / totalCalls) * 100).toFixed(1));
    const duration_percent =
      totalDurationMs > 0 ? Number(((data.duration_ms / totalDurationMs) * 100).toFixed(1)) : 0;
    items.push({
      tool_name,
      calls: data.calls,
      calls_percent,
      duration_ms: Math.round(data.duration_ms),
      duration_percent,
    });
  }

  // 3. 按调用量降序排序
  items.sort((a, b) => b.calls - a.calls);

  const topTools = items.slice(0, 3);
  const otherTools = items.slice(3);

  let otherCallsTotal = 0;
  let otherDurationTotal = 0;
  for (const item of otherTools) {
    otherCallsTotal += item.calls;
    otherDurationTotal += item.duration_ms;
  }

  const otherCallsPercent = Number(((otherCallsTotal / totalCalls) * 100).toFixed(1));
  const otherDurationPercent =
    totalDurationMs > 0 ? Number(((otherDurationTotal / totalDurationMs) * 100).toFixed(1)) : 0;

  return {
    totalCalls,
    totalDurationMs: Math.round(totalDurationMs),
    topTools,
    otherTools,
    otherCallsTotal,
    otherCallsPercent,
    otherDurationTotal: Math.round(otherDurationTotal),
    otherDurationPercent,
  };
}

interface ToolCompositionCardProps {
  dailyRecords: ToolStabilityDaily[];
  days: number;
  onDaysChange?: (days: number) => void;
  className?: string;
}

export const ToolCompositionCard: React.FC<ToolCompositionCardProps> = ({
  dailyRecords,
  days,
  onDaysChange,
  className = '',
}) => {
  const [expanded, setExpanded] = useState<boolean>(false);
  const summary = useMemo(() => computeToolComposition(dailyRecords), [dailyRecords]);

  if (summary.totalCalls === 0) {
    return null;
  }

  return (
    <div
      data-testid="tool-composition-card"
      className={`rounded-xl border border-border/60 bg-background/50 p-4 space-y-3.5 ${className}`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
        <div className="flex items-center gap-2">
          <PieChart className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            周期工具构成分析 (Tool Composition)
          </h3>
          <span className="text-xs text-muted-foreground font-mono">
            (共 {summary.totalCalls.toLocaleString()} 次调用)
          </span>
        </div>

        {/* 7天 / 30天切换 */}
        {onDaysChange && (
          <div className="flex items-center gap-1 bg-muted/40 p-0.5 rounded-lg border border-border/40 text-xs">
            <button
              type="button"
              onClick={() => onDaysChange(7)}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                days === 7 ? 'bg-background shadow-xs font-medium text-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              7 天
            </button>
            <button
              type="button"
              onClick={() => onDaysChange(30)}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                days === 30 ? 'bg-background shadow-xs font-medium text-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              30 天
            </button>
          </div>
        )}
      </div>

      {/* 边界提示 */}
      <div className="flex items-start gap-1.5 p-2 rounded-lg bg-muted/20 border border-border/30 text-[11px] text-muted-foreground">
        <Info className="w-3.5 h-3.5 mt-0.5 text-primary/70 shrink-0" />
        <span>
          调用占比与累计耗时占比分别统计。并行调用的执行耗时可能重叠，累计耗时占比不代表实际墙钟时间占比；本视图仅展示调用与耗时结构，不设成本占比。
        </span>
      </div>

      {/* 前三项突出展示 */}
      <div className="space-y-2">
        {summary.topTools.map((tool, idx) => (
          <div
            key={tool.tool_name}
            className="flex flex-col sm:flex-row sm:items-center justify-between p-2.5 rounded-lg border border-border/40 bg-muted/15 gap-2 text-xs"
          >
            <div className="flex items-center gap-2">
              <span className="w-4 h-4 flex items-center justify-center rounded-full bg-primary/20 text-primary font-bold text-[10px]">
                {idx + 1}
              </span>
              <span className="font-semibold text-foreground break-all">{tool.tool_name}</span>
            </div>

            <div className="flex items-center gap-4 text-muted-foreground shrink-0 text-[11px]">
              <div className="flex items-center gap-1">
                <Hash className="w-3 h-3 text-primary/60" />
                <span>
                  {tool.calls.toLocaleString()} 次 ({tool.calls_percent}%)
                </span>
              </div>
              <div className="flex items-center gap-1">
                <Clock className="w-3 h-3 text-amber-500/60" />
                <span>
                  {tool.duration_ms.toLocaleString()} ms ({tool.duration_percent}%)
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 其余折叠展示 */}
      {summary.otherTools.length > 0 && (
        <div className="border-t border-border/30 pt-2 space-y-2 text-xs">
          <button
            type="button"
            data-testid="toggle-other-tools"
            onClick={() => setExpanded(!expanded)}
            className="w-full flex items-center justify-between p-2 rounded-lg hover:bg-muted/30 transition-colors text-muted-foreground"
          >
            <div className="flex items-center gap-1.5">
              {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              <span>
                其他 {summary.otherTools.length} 项工具 ({summary.otherCallsTotal.toLocaleString()} 次 · {summary.otherCallsPercent}%)
              </span>
            </div>
            <span className="text-[11px] font-mono">
              耗时: {summary.otherDurationPercent}%
            </span>
          </button>

          {expanded && (
            <div data-testid="other-tools-container" className="pl-4 space-y-1.5 pt-1">
              {summary.otherTools.map((tool) => (
                <div
                  key={tool.tool_name}
                  className="flex items-center justify-between py-1 px-2 rounded bg-muted/10 text-[11px] text-muted-foreground"
                >
                  <span className="font-mono truncate">{tool.tool_name}</span>
                  <div className="flex items-center gap-3 shrink-0">
                    <span>{tool.calls} 次 ({tool.calls_percent}%)</span>
                    <span>{tool.duration_percent}% 耗时</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
