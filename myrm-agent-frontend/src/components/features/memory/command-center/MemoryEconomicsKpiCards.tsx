'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryCommandEconomicsDashboard (POS: 记忆命令中心经济学数据契约)
 *
 * [OUTPUT]
 * MemoryEconomicsKpiCards: 4 大核心 KPI 指标卡片（三阶段时延细分、前缀缓存保持率、有效 ROI、沉睡收益预估）。
 *
 * [POS]
 * 记忆命令中心经济学指标卡片组件。提供高对比三阶段耗时水平细分条与 ROI 效能概览。
 */

import React from 'react';
import { Cpu, DollarSign, Gauge, Zap } from 'lucide-react';

import type { MemoryCommandEconomicsDashboard } from '@/services/memory/commandCenter';

interface MemoryEconomicsKpiCardsProps {
  cost: MemoryCommandEconomicsDashboard['cost_profile'] | undefined;
  savings: number;
  parasiticCount: number;
}

export const MemoryEconomicsKpiCards: React.FC<MemoryEconomicsKpiCardsProps> = ({
  cost,
  savings,
  parasiticCount,
}) => {
  const retrievalMs = cost?.retrieval_ms ?? 0;
  const constructionMs = cost?.construction_ms ?? 0;
  const injectionMs = cost?.injection_overhead_ms ?? 0;
  const totalPhaseMs = retrievalMs + constructionMs + injectionMs;
  const retrievalPct = totalPhaseMs > 0 ? Math.round((retrievalMs / totalPhaseMs) * 100) : 100;
  const constructionPct = totalPhaseMs > 0 ? Math.round((constructionMs / totalPhaseMs) * 100) : 0;
  const injectionPct = totalPhaseMs > 0 ? Math.max(0, 100 - retrievalPct - constructionPct) : 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
      {/* Metric 1: Three-Phase Latency */}
      <div className="p-4 rounded-xl border border-border/40 bg-background/50 flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5 font-medium">
            <Zap className="w-3.5 h-3.5 text-amber-500" />
            检索阶段时延
          </span>
          <span>平均</span>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
            {retrievalMs}
          </span>
          <span className="text-xs text-muted-foreground">ms</span>
        </div>
        <div className="text-[11px] text-muted-foreground/80 flex items-center justify-between">
          <span>后台构建: {constructionMs} ms</span>
          <span>注入开销: {injectionMs} ms</span>
        </div>
        {totalPhaseMs > 0 && (
          <div className="flex flex-col gap-1 pt-1 border-t border-border/20">
            <div className="h-1.5 w-full rounded-full overflow-hidden flex bg-muted/60">
              <div
                className="bg-amber-500 transition-all duration-300"
                style={{ width: `${retrievalPct}%` }}
                title={`检索: ${retrievalPct}%`}
              />
              <div
                className="bg-sky-500 transition-all duration-300"
                style={{ width: `${constructionPct}%` }}
                title={`构建: ${constructionPct}%`}
              />
              <div
                className="bg-indigo-500 transition-all duration-300"
                style={{ width: `${injectionPct}%` }}
                title={`注入: ${injectionPct}%`}
              />
            </div>
            <div className="flex items-center justify-between text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                检索 {retrievalPct}%
              </span>
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-sky-500" />
                构建 {constructionPct}%
              </span>
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                注入 {injectionPct}%
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Metric 2: Cache Preservation */}
      <div className="p-4 rounded-xl border border-border/40 bg-background/50 flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5 font-medium">
            <Cpu className="w-3.5 h-3.5 text-blue-500" />
            前缀缓存保持率
          </span>
          <span>Cache</span>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
            {Math.round((cost?.cache_preservation_score ?? 1) * 100)}%
          </span>
          <span className="text-xs text-muted-foreground">保持率</span>
        </div>
        <div className="text-[11px] text-muted-foreground/80">
          {cost?.cache_friendly ? '前缀对齐良好，命中最大化' : '提示词前缀需进一步对齐'}
        </div>
      </div>

      {/* Metric 3: Effective Recall ROI */}
      <div className="p-4 rounded-xl border border-border/40 bg-background/50 flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5 font-medium">
            <Gauge className="w-3.5 h-3.5 text-emerald-500" />
            记忆召回有效 ROI
          </span>
          <span>利用率</span>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
            {cost?.roi_percentage ?? 0}%
          </span>
          <span className="text-xs text-muted-foreground">有效转化</span>
        </div>
        <div className="text-[11px] text-muted-foreground/80">
          引用 Tokens: {cost?.effective_cited_tokens ?? 0} / 装载: {cost?.estimated_memory_tokens ?? 0}
        </div>
      </div>

      {/* Metric 4: Potential Savings */}
      <div className="p-4 rounded-xl border border-border/40 bg-background/50 flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5 font-medium">
            <DollarSign className="w-3.5 h-3.5 text-purple-500" />
            治理沉睡收益预估
          </span>
          <span>节约</span>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
            ${savings.toFixed(4)}
          </span>
          <span className="text-xs text-muted-foreground">USD / 周期</span>
        </div>
        <div className="text-[11px] text-muted-foreground/80">
          {parasiticCount > 0
            ? `沉睡记忆项: ${parasiticCount} 条待清理 · 按主流模型 $3.00/1M Tokens 基准测算`
            : '全量记忆保持高频活跃与有效引用 · 无沉睡冗余'}
        </div>
      </div>
    </div>
  );
};
