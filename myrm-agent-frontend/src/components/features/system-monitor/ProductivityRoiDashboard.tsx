'use client';

/**
 * [INPUT]
 * - ./types::MonthlyProductivitySummary (POS: 生产力汇总契约)
 * - lucide-react::Briefcase, TrendingUp, DollarSign, Clock, CheckCircle2, Sparkles, BarChart3 (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - ProductivityRoiDashboard: 白领生产力总览与工时挽回投资回报全景看板
 *
 * [POS]
 * src/components/features/system-monitor/ProductivityRoiDashboard.tsx — 生产力 ROI 与工时挽回透视大盘组件。
 */

import React from 'react';
import {
  Briefcase,
  TrendingUp,
  DollarSign,
  Clock,
  CheckCircle2,
  Sparkles,
  BarChart3,
} from 'lucide-react';
import type { MonthlyProductivitySummary } from './types';

interface ProductivityRoiDashboardProps {
  summary: MonthlyProductivitySummary;
  className?: string;
}

export const ProductivityRoiDashboard: React.FC<ProductivityRoiDashboardProps> = ({
  summary,
  className = '',
}) => {
  const avgCostPerHour =
    summary.total_hours_saved > 0
      ? summary.total_compute_cost_usd / summary.total_hours_saved
      : 0.0;

  return (
    <div
      className={`bg-card border border-border rounded-xl shadow-sm overflow-hidden flex flex-col ${className}`}
    >
      {/* 头部标题与月份 */}
      <div className="p-4 sm:p-5 border-b border-border bg-muted/20 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Briefcase className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
              白领劳务效能与生产力 ROI 看板
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground border border-border">
                {summary.month}
              </span>
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              累计接管 {summary.total_tasks_automated} 项高频复杂劳务，相当于增加了一位全职高能搭档
            </p>
          </div>
        </div>

        {/* 综合生产力 ROI 突出展示 */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-300">
          <TrendingUp className="w-4 h-4 text-emerald-500 shrink-0" />
          <div>
            <div className="text-[10px] opacity-80">综合生产力 ROI</div>
            <div className="text-sm font-bold font-mono">
              {summary.overall_roi_ratio.toFixed(1)}× 收益倍率
            </div>
          </div>
        </div>
      </div>

      {/* 核心指标四宫格 */}
      <div className="p-4 sm:p-5 grid grid-cols-2 lg:grid-cols-4 gap-3 border-b border-border bg-background">
        <div className="p-3 rounded-lg border border-border bg-muted/20 space-y-1">
          <div className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Clock className="w-3.5 h-3.5 text-primary" />
            累计挽回工时
          </div>
          <div className="text-lg font-bold font-mono text-foreground">
            {summary.total_hours_saved.toFixed(1)}{' '}
            <span className="text-xs font-normal text-muted-foreground">小时</span>
          </div>
        </div>

        <div className="p-3 rounded-lg border border-border bg-muted/20 space-y-1">
          <div className="text-[11px] text-muted-foreground flex items-center gap-1">
            <DollarSign className="w-3.5 h-3.5 text-emerald-500" />
            等效人工商业价值
          </div>
          <div className="text-lg font-bold font-mono text-emerald-600 dark:text-emerald-400">
            ${summary.total_saved_value_usd.toFixed(2)}
          </div>
        </div>

        <div className="p-3 rounded-lg border border-border bg-muted/20 space-y-1">
          <div className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5 text-amber-500" />
            累计算力投入支出
          </div>
          <div className="text-lg font-bold font-mono text-foreground">
            ${summary.total_compute_cost_usd.toFixed(2)}
          </div>
        </div>

        <div className="p-3 rounded-lg border border-border bg-muted/20 space-y-1">
          <div className="text-[11px] text-muted-foreground flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-blue-500" />
            每挽回 1h 工时成本
          </div>
          <div className="text-lg font-bold font-mono text-blue-600 dark:text-blue-400">
            ${avgCostPerHour.toFixed(2)}
          </div>
        </div>
      </div>

      {/* 高频省时任务行为排行榜 */}
      <div className="p-4 sm:p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
            <BarChart3 className="w-3.5 h-3.5 text-primary" />
            高频劳务节省工时分类排行 (Top Labor Savings)
          </h4>
          <span className="text-[11px] text-muted-foreground">
            基准工时标准: $35.00/小时
          </span>
        </div>

        <div className="space-y-2">
          {summary.top_saving_categories.map((cat, idx) => {
            const pct =
              summary.total_hours_saved > 0
                ? (cat.total_hours_saved / summary.total_hours_saved) * 100
                : 0;

            return (
              <div
                key={idx}
                className="p-3 rounded-lg border border-border/60 bg-muted/10 space-y-1.5 text-xs"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-muted-foreground text-[10px]">
                      0{idx + 1}
                    </span>
                    <span className="font-medium text-foreground">{cat.label}</span>
                  </div>
                  <div className="flex items-center gap-2 font-mono text-[11px]">
                    <span className="text-muted-foreground">{cat.count} 次</span>
                    <span className="font-semibold text-primary">
                      {cat.total_hours_saved.toFixed(1)}h ({pct.toFixed(0)}%)
                    </span>
                  </div>
                </div>

                <div className="h-1.5 w-full rounded-full bg-muted/60 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary/80 transition-all duration-300"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
