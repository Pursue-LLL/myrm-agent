/**
 * [INPUT]
 * @/services/memory/vectorSpaceGuard::SpaceStatusResponse (POS: vector space status type)
 * lucide-react::ShieldCheck, Layers, Hash, Activity, RefreshCw (POS: UI icons)
 *
 * [OUTPUT]
 * Component: VectorSpaceGuardHudBar
 *
 * [POS]
 * Real-time HUD summary bar displaying vector space metadata, dimension, model base,
 * metric type, and registered vector volume. Strictly typed, accessible, < 200 lines.
 */

import React from 'react';
import { ShieldCheck, Layers, Hash, Activity, RefreshCw } from 'lucide-react';
import type { SpaceStatusResponse } from '@/services/memory/vectorSpaceGuard';

interface VectorSpaceGuardHudBarProps {
  status: SpaceStatusResponse | null;
  isLoading: boolean;
  onRefresh: () => void;
}

export const VectorSpaceGuardHudBar: React.FC<VectorSpaceGuardHudBarProps> = ({
  status,
  isLoading,
  onRefresh,
}) => {
  const fp = status?.fingerprint;
  const isRegistered = status?.has_registered_space ?? false;

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl bg-card border border-border shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-primary/10 text-primary">
          <ShieldCheck className="w-5 h-5" aria-hidden="true" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-foreground text-sm tracking-tight">
              向量空间一致性守卫
            </h3>
            <span
              className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                isRegistered
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                  : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
              }`}
            >
              {isRegistered ? '已受保护' : '未注册空间'}
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            目标集合：<span className="font-mono text-foreground font-medium">{status?.collection ?? '未绑定'}</span>
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-6 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
          <span>基底模型:</span>
          <span className="font-mono font-medium text-foreground">
            {fp ? `${fp.provider_id}/${fp.model_name}` : '暂无'}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <Hash className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
          <span>维度:</span>
          <span className="font-mono font-medium text-foreground">
            {fp ? `${fp.vector_dimension}d (${fp.metric_type})` : '暂无'}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
          <span>已索引向量:</span>
          <span className="font-mono font-medium text-foreground">
            {status?.total_vectors_indexed ?? 0}
          </span>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          aria-label="刷新空间状态"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`}
            aria-hidden="true"
          />
          <span>刷新</span>
        </button>
      </div>
    </header>
  );
};
