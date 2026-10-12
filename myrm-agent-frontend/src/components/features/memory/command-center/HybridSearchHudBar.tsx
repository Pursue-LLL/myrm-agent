/**
 * HUD Telemetry Bar for Dual-Engine Hybrid Search and Circuit Breaker.
 */

import React from 'react';
import { Activity, AlertTriangle, CheckCircle2, RefreshCw, Zap, ShieldAlert } from 'lucide-react';
import type { HybridEngineStatsDTO } from '@/services/memory/hybridSearch';

interface HybridSearchHudBarProps {
  stats: HybridEngineStatsDTO;
  isLoading: boolean;
  onRefresh: () => void;
  onTripBreaker: () => void;
  onResetBreaker: () => void;
}

export const HybridSearchHudBar: React.FC<HybridSearchHudBarProps> = ({
  stats,
  isLoading,
  onRefresh,
  onTripBreaker,
  onResetBreaker,
}) => {
  const cbState = stats.circuit_breaker.state;

  const getModeBadge = (mode: string) => {
    switch (mode) {
      case 'hybrid_rrf':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
            <Zap className="h-3 w-3" aria-hidden="true" />
            双引擎 RRF 融合
          </span>
        );
      case 'degraded_fallback':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400">
            <AlertTriangle className="h-3 w-3" aria-hidden="true" />
            降级纯 FTS5 兜底
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 px-2 py-0.5 text-xs font-medium text-blue-600 dark:text-blue-400">
            <Activity className="h-3 w-3" aria-hidden="true" />
            SQLite FTS5 单引擎
          </span>
        );
    }
  };

  const getBreakerBadge = (state: string) => {
    switch (state) {
      case 'open':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 px-2 py-0.5 text-xs font-semibold text-rose-600 dark:text-rose-400">
            <ShieldAlert className="h-3 w-3" aria-hidden="true" />
            熔断跳闸 (OPEN)
          </span>
        );
      case 'half_open':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-600 dark:text-amber-400">
            <RefreshCw className="h-3 w-3 animate-spin" aria-hidden="true" />
            半开自愈探测 (HALF_OPEN)
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
            链路健康闭合 (CLOSED)
          </span>
        );
    }
  };

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border/60 bg-muted/30 p-4">
      <div className="flex flex-wrap items-center gap-6">
        <div>
          <div className="text-xs text-muted-foreground">检索模式</div>
          <div className="mt-1 flex items-center gap-2">
            {getModeBadge(stats.active_mode)}
          </div>
        </div>

        <div>
          <div className="text-xs text-muted-foreground">断路器守卫</div>
          <div className="mt-1 flex items-center gap-2">
            {getBreakerBadge(cbState)}
          </div>
        </div>

        <div>
          <div className="text-xs text-muted-foreground">FTS5 记忆索引量</div>
          <div className="mt-1 text-sm font-semibold tracking-tight">
            {stats.total_items} 条
          </div>
        </div>

        <div>
          <div className="text-xs text-muted-foreground">离线同义词图谱</div>
          <div className="mt-1 text-sm font-semibold tracking-tight">
            {stats.synonym_terms_count} 节点
          </div>
        </div>

        <div>
          <div className="text-xs text-muted-foreground">断路器跳闸次数</div>
          <div className="mt-1 text-sm font-semibold tracking-tight">
            {stats.circuit_breaker.tripped_count} 次
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {cbState === 'open' ? (
          <button
            type="button"
            onClick={onResetBreaker}
            disabled={isLoading}
            aria-label="复位断路器并恢复向量检索"
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white shadow hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            复位闭合断路器
          </button>
        ) : (
          <button
            type="button"
            onClick={onTripBreaker}
            disabled={isLoading}
            aria-label="模拟向量服务故障触发熔断"
            className="inline-flex items-center gap-1.5 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/20 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50"
          >
            <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
            模拟故障熔断
          </button>
        )}

        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          aria-label="刷新混合检索遥测指标"
          className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} aria-hidden="true" />
          刷新遥测
        </button>
      </div>
    </header>
  );
};
