'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::getMemoryEconomics (POS: 记忆命令中心经济学数据接口与契约)
 * ./MemoryEconomicsKpiCards::MemoryEconomicsKpiCards (POS: 4 大核心 KPI 指标卡片与三阶段细分占比)
 * ./MemoryParasiticGovernanceList::MemoryParasiticGovernanceList (POS: 低效沉睡记忆治理池与归档交互)
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
  CheckCircle2,
  HelpCircle,
  Layers,
  RefreshCw,
  Sparkles,
  TrendingUp,
} from 'lucide-react';

import {
  executeMemoryAction,
  getMemoryEconomics,
  type MemoryCommandEconomicsDashboard,
  type MemoryCommandParasiticMemory,
} from '@/services/memory/commandCenter';
import { cn } from '@/lib/utils/classnameUtils';
import { MemoryEconomicsKpiCards } from './MemoryEconomicsKpiCards';
import { MemoryParasiticGovernanceList } from './MemoryParasiticGovernanceList';

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

  const roiBadge = getRoiBadge(cost?.roi_grade);

  return (
    <div className={cn('p-5 sm:p-6 rounded-2xl border border-border/60 bg-card/30 backdrop-blur-sm flex flex-col gap-6', className)}>
      {/* Header with Title and ROI Grade */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary shrink-0">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-foreground">长程记忆经济学剖析器</h3>
              <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium border', roiBadge.color)}>
                ROI: {roiBadge.label}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              长程有状态任务开销拆解 · 检索/构建/注入三阶段时延与沉睡记忆精细化治理
            </p>
          </div>
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
      <MemoryEconomicsKpiCards
        cost={cost}
        savings={savings}
        parasiticCount={parasitic.length}
      />

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
        <MemoryParasiticGovernanceList
          parasitic={parasitic}
          archivingId={archivingId}
          archivingAll={archivingAll}
          confirmArchiveAll={confirmArchiveAll}
          onSetConfirmArchiveAll={setConfirmArchiveAll}
          onArchive={handleArchive}
          onArchiveAll={handleArchiveAll}
        />
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
