'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::getMemoryEconomics (POS: 记忆命令中心经济学数据接口与契约)
 *
 * [OUTPUT]
 * MemoryEconomicsPanel: Interactive long-horizon memory economics profiler dashboard.
 *
 * [POS]
 * 前端记忆命令中心经济学剖析组件。可视化长程多轮有状态任务的三阶段开销、Prompt Cache 保持率与沉睡记忆治理。
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Archive,
  Check,
  CheckCircle2,
  Cpu,
  DollarSign,
  Gauge,
  HelpCircle,
  Layers,
  RefreshCw,
  Sparkles,
  TrendingUp,
  X,
  Zap,
} from 'lucide-react';

import {
  executeMemoryAction,
  getMemoryEconomics,
  type MemoryCommandEconomicsDashboard,
  type MemoryCommandParasiticMemory,
} from '@/services/memory/commandCenter';
import { cn } from '@/lib/utils/classnameUtils';

interface MemoryEconomicsPanelProps {
  className?: string;
  initialDashboard?: MemoryCommandEconomicsDashboard | null;
  onRefreshParent?: () => void;
}

export const MemoryEconomicsPanel: React.FC<MemoryEconomicsPanelProps> = ({
  className,
  initialDashboard,
  onRefreshParent,
}) => {
  const [dashboard, setDashboard] = useState<MemoryCommandEconomicsDashboard | null>(initialDashboard || null);
  const [loading, setLoading] = useState<boolean>(!initialDashboard);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const [archivingAll, setArchivingAll] = useState<boolean>(false);
  const [confirmArchiveAll, setConfirmArchiveAll] = useState<boolean>(false);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [archivedIds, setArchivedIds] = useState<Set<string>>(new Set());

  const fetchEconomics = useCallback(async () => {
    try {
      const data = await getMemoryEconomics({ limitTurns: 50 });
      setDashboard(data);
    } catch {
      // Graceful fallback
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (!initialDashboard) {
      fetchEconomics();
    } else {
      setDashboard(initialDashboard);
    }
  }, [initialDashboard, fetchEconomics]);

  const handleArchive = async (item: MemoryCommandParasiticMemory) => {
    setArchivingId(item.memory_id);
    // Optimistically hide the archived memory immediately
    setArchivedIds((prev) => new Set(prev).add(item.memory_id));
    try {
      await executeMemoryAction({
        target_kind: 'memory',
        target_id: item.memory_id,
        action: 'forget',
        memory_type: item.memory_type,
      });
      setActionNotice(`已成功归档记忆 "${item.content_preview.slice(0, 20)}..."`);
      await fetchEconomics();
      onRefreshParent?.();
    } catch {
      // Rollback on error
      setArchivedIds((prev) => {
        const next = new Set(prev);
        next.delete(item.memory_id);
        return next;
      });
      setActionNotice('归档操作失败，请重试');
    } finally {
      setArchivingId(null);
      setTimeout(() => setActionNotice(null), 4000);
    }
  };

  const handleArchiveAll = async (items: MemoryCommandParasiticMemory[]) => {
    if (!items.length || archivingAll) {
      return;
    }
    setConfirmArchiveAll(false);
    setArchivingAll(true);
    const itemIds = items.map((i) => i.memory_id);
    // Optimistically hide all targeted memories immediately
    setArchivedIds((prev) => {
      const next = new Set(prev);
      itemIds.forEach((id) => next.add(id));
      return next;
    });
    try {
      await Promise.all(
        items.map((item) =>
          executeMemoryAction({
            target_kind: 'memory',
            target_id: item.memory_id,
            action: 'forget',
            memory_type: item.memory_type,
          })
        )
      );
      setActionNotice(`已成功批量归档 ${items.length} 条沉睡记忆`);
      await fetchEconomics();
      onRefreshParent?.();
    } catch {
      // Rollback on error
      setArchivedIds((prev) => {
        const next = new Set(prev);
        itemIds.forEach((id) => next.delete(id));
        return next;
      });
      setActionNotice('批量归档失败，请重试');
    } finally {
      setArchivingAll(false);
      setTimeout(() => setActionNotice(null), 4000);
    }
  };

  if (loading && !dashboard) {
    return (
      <div className={cn('p-6 rounded-2xl border border-border/50 bg-card/40 flex items-center justify-center py-16', className)}>
        <div className="flex items-center gap-3 text-muted-foreground">
          <RefreshCw className="w-5 h-5 animate-spin text-primary" />
          <span className="text-sm font-medium">正在分析长程记忆经济学与三阶段开销...</span>
        </div>
      </div>
    );
  }

  const cost = dashboard?.cost_profile;
  const trajectories = dashboard?.turn_trajectories || [];
  const parasitic = (dashboard?.parasitic_memories || []).filter(
    (item) => !archivedIds.has(item.memory_id)
  );
  const totalWastedTokens = parasitic.reduce((acc, p) => acc + (p.wasted_tokens_estimated || 0), 0);
  const dynamicSavingsUsd = Number(((totalWastedTokens / 1_000_000.0) * 3.0).toFixed(4));
  const savings = parasitic.length > 0 ? dynamicSavingsUsd : 0;
  const recommendations = dashboard?.recommendations || [];

  const retrievalMs = cost?.retrieval_ms ?? 0;
  const constructionMs = cost?.construction_ms ?? 0;
  const injectionMs = cost?.injection_overhead_ms ?? 0;
  const totalPhaseMs = retrievalMs + constructionMs + injectionMs;
  const retrievalPct = totalPhaseMs > 0 ? Math.round((retrievalMs / totalPhaseMs) * 100) : 100;
  const constructionPct = totalPhaseMs > 0 ? Math.round((constructionMs / totalPhaseMs) * 100) : 0;
  const injectionPct = totalPhaseMs > 0 ? Math.max(0, 100 - retrievalPct - constructionPct) : 0;

  const getRoiBadge = (grade: string | undefined) => {
    switch (grade) {
      case 'optimal':
        return {
          label: '卓越 (>=50%)',
          color: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
        };
      case 'healthy':
        return {
          label: '健康 (25~50%)',
          color: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20',
        };
      case 'diluted':
        return {
          label: '稀释 (10~25%)',
          color: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
        };
      default:
        return {
          label: '严重低效 (<10%)',
          color: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
        };
    }
  };

  const badge = getRoiBadge(cost?.roi_grade);

  return (
    <div className={cn('flex flex-col gap-6 p-4 sm:p-6 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-sm', className)}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-border/40">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-xl bg-primary/10 text-primary">
              <TrendingUp className="w-5 h-5" />
            </span>
            <h3 className="text-base sm:text-lg font-semibold tracking-tight text-foreground">
              长程记忆经济学剖析看板
            </h3>
            <span className={cn('px-2.5 py-0.5 text-xs font-semibold rounded-full border', badge.color)}>
              ROI {badge.label}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            拆解构建、检索与注入三阶段耗时，监督长程会话召回 ROI 与提示词前缀缓存对齐。
          </p>
        </div>

        <button
          onClick={() => {
            setRefreshing(true);
            fetchEconomics();
          }}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border hover:bg-muted/60 transition-colors self-start sm:self-center"
        >
          <RefreshCw className={cn('w-3.5 h-3.5', refreshing && 'animate-spin')} />
          刷新分析
        </button>
      </div>

      {actionNotice && (
        <div className="px-4 py-2.5 rounded-xl bg-primary/10 border border-primary/20 text-xs font-medium text-primary flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{actionNotice}</span>
        </div>
      )}

      {/* Top 4 Metric KPI Cards */}
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
            {parasitic.length > 0
              ? `沉睡记忆项: ${parasitic.length} 条待清理 · 按主流模型 $3.00/1M Tokens 基准测算`
              : '全量记忆保持高频活跃与有效引用 · 无沉睡冗余'}
          </div>
        </div>
      </div>

      {/* Trajectory and Parasitic Candidates Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left: Turn Trajectory (7 cols) */}
        <div className="lg:col-span-7 flex flex-col gap-3 p-4 rounded-xl border border-border/40 bg-background/40">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary" />
              <h4 className="text-xs sm:text-sm font-semibold text-foreground">
                长程轮次记忆装载与时序轨迹
              </h4>
            </div>
            <span className="text-[11px] text-muted-foreground">最近 {trajectories.length} 轮</span>
          </div>

          {trajectories.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              暂无多轮会话轨迹，交互后将实时生成经济学剖析。
            </div>
          ) : (
            <div className="flex flex-col gap-2 max-h-[260px] overflow-y-auto pr-1">
              {trajectories.map((t) => (
                <div
                  key={t.turn_index}
                  className="flex items-center justify-between p-2.5 rounded-lg border border-border/30 bg-card/40 hover:bg-card/70 transition-colors text-xs"
                >
                  <div className="flex items-center gap-2.5">
                    <span className="w-6 h-6 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center text-[10px]">
                      {t.turn_index}
                    </span>
                    <div>
                      <div className="font-medium text-foreground">
                        装载 {t.injected_tokens} Tokens · 引用 {t.cited_tokens} Tokens
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        检索耗时: {t.retrieval_ms}ms · 缓存命中: {t.cached_tokens} Tokens
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold text-foreground">{t.roi_percentage}% ROI</div>
                    <div className="text-[10px] text-emerald-500 font-medium">
                      {t.cache_aligned ? '前缀对齐' : '需优化'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Parasitic Stale Memories (5 cols) */}
        <div className="lg:col-span-5 flex flex-col gap-3 p-4 rounded-xl border border-border/40 bg-background/40">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              <h4 className="text-xs sm:text-sm font-semibold text-foreground">
                低效沉睡记忆治理池
              </h4>
            </div>
            {parasitic.length > 0 ? (
              confirmArchiveAll ? (
                <div className="flex items-center gap-1.5 animate-in fade-in zoom-in-95 duration-150">
                  <span className="text-[11px] text-destructive font-medium hidden sm:inline">
                    确认全部归档?
                  </span>
                  <button
                    onClick={() => handleArchiveAll(parasitic)}
                    disabled={archivingAll || archivingId !== null}
                    className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-md bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-all shadow-sm active:scale-95 disabled:opacity-50"
                  >
                    <Check className="w-3 h-3" />
                    确认
                  </button>
                  <button
                    onClick={() => setConfirmArchiveAll(false)}
                    disabled={archivingAll}
                    className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-md bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-all active:scale-95"
                  >
                    <X className="w-3 h-3" />
                    取消
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmArchiveAll(true)}
                  disabled={archivingAll || archivingId !== null}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/25 transition-all shadow-sm active:scale-95 disabled:opacity-50"
                >
                  <Archive className="w-3 h-3" />
                  {archivingAll ? '批量归档中...' : `一键归档全部 (${parasitic.length})`}
                </button>
              )
            ) : (
              <span className="text-[11px] text-muted-foreground">0 条待处置</span>
            )}
          </div>

          {parasitic.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground flex flex-col items-center gap-1.5">
              <CheckCircle2 className="w-5 h-5 text-emerald-500" />
              <span>当前记忆库极具活力，未检出低效沉睡记忆。</span>
            </div>
          ) : (
            <div className="flex flex-col gap-2 max-h-[260px] overflow-y-auto pr-1">
              {parasitic.map((item) => (
                <div
                  key={item.memory_id}
                  className="p-2.5 rounded-lg border border-border/30 bg-card/40 flex flex-col gap-1.5 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-foreground truncate max-w-[170px]">
                      {item.content_preview}
                    </span>
                    <button
                      onClick={() => handleArchive(item)}
                      disabled={archivingId === item.memory_id}
                      className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded border border-border hover:bg-muted text-foreground transition-colors shrink-0"
                    >
                      <Archive className="w-3 h-3 text-muted-foreground" />
                      {archivingId === item.memory_id ? '归档中...' : '一键归档'}
                    </button>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>装载 {item.injected_turns_count} 轮 · 引用 0 次</span>
                    <span className="text-rose-500 font-medium">浪费 ~{item.wasted_tokens_estimated} T</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Actionable Recommendations */}
      {recommendations.length > 0 && (
        <div className="p-3.5 rounded-xl border border-primary/20 bg-primary/5 flex flex-col gap-1.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-primary">
            <Sparkles className="w-4 h-4" />
            <span>智能体记忆架构师治理建议</span>
          </div>
          <div className="flex flex-col gap-1 text-xs text-foreground/90 pl-5 list-disc">
            {recommendations.map((rec, idx) => (
              <div key={idx} className="relative before:content-['•'] before:absolute before:-left-3.5 before:text-primary">
                {rec}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
