/**
 * [INPUT]
 * @/services/memory::QuadrupleRetrievalStatsDTO
 * lucide-react::(Compass, Zap, Cpu, Activity, RefreshCw)
 *
 * [OUTPUT]
 * Component: QuadrupleRetrievalHudBar
 *
 * [POS]
 * Top HUD metric header bar for Item 127 Goal-Driven Quadruple Retrieval & Reasoner Suite.
 * Displays key metrics: Total Indexed Memories, 4-Way Active Channels, Avg Latency, Weights.
 * A11y compliant: Semantic header, native buttons, visible focus rings, zero bare chevron entities.
 * Strict typing: Zero `any`. Single file < 200 lines.
 */

import React from 'react';
import { Compass, Zap, Cpu, Activity, RefreshCw } from 'lucide-react';
import type { QuadrupleRetrievalStatsDTO } from '@/services/memory';

interface QuadrupleRetrievalHudBarProps {
  stats: QuadrupleRetrievalStatsDTO;
  isLoading: boolean;
  onRefresh: () => void;
}

export const QuadrupleRetrievalHudBar: React.FC<QuadrupleRetrievalHudBarProps> = ({
  stats,
  isLoading,
  onRefresh,
}) => {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-lg border border-border/70 bg-card/60 backdrop-blur-sm">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-primary/10 text-primary">
            <Compass className="w-4 h-4" aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              MemOS Quadruple Engine
            </h3>
            <p className="text-sm font-medium text-foreground">
              Goal-Driven 4-Way Recall &amp; Reasoner
            </p>
          </div>
        </div>

        <div className="h-6 w-px bg-border/60 hidden sm:block" aria-hidden="true" />

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium">
            <Cpu className="w-3.5 h-3.5" aria-hidden="true" />
            Indexed: {stats.total_indexed_memories}
          </span>
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-blue-500/10 text-blue-600 dark:text-blue-400 font-medium">
            <Activity className="w-3.5 h-3.5" aria-hidden="true" />
            Channels: {stats.active_channels_count} / 4 Active
          </span>
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-purple-500/10 text-purple-600 dark:text-purple-400 font-medium">
            <Zap className="w-3.5 h-3.5" aria-hidden="true" />
            Latency: {stats.average_latency_ms.toFixed(1)} ms
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          aria-label="刷新四路检索引擎指标"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border border-border/80 bg-background hover:bg-muted/60 transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`}
            aria-hidden="true"
          />
          刷新指标
        </button>
      </div>
    </header>
  );
};
