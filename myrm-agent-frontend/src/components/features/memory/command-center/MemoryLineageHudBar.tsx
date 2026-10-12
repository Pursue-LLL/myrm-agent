/**
 * [INPUT]
 * @/services/memory::LineageStatsDTO
 * lucide-react::(GitFork, GitCommit, Network, Layers, RefreshCw, Zap)
 *
 * [OUTPUT]
 * Component: MemoryLineageHudBar
 *
 * [POS]
 * Top HUD metric header bar for Item 126 Graph Memory Reorganization & Lineage Traceability.
 * Displays key metrics: Active Nodes, Superseded Versions, Semantic Edges, Max Depth.
 * A11y compliant: Semantic header, native buttons, visible focus rings, zero bare chevron entities.
 * Strict typing: Zero `any`. Single file < 200 lines.
 */

import React from 'react';
import { GitFork, GitCommit, Network, Layers, RefreshCw, Zap } from 'lucide-react';
import type { LineageStatsDTO } from '@/services/memory';

interface MemoryLineageHudBarProps {
  stats: LineageStatsDTO;
  isLoading: boolean;
  isReorganizing: boolean;
  onRefresh: () => void;
  onTriggerReorganize: () => void;
}

export const MemoryLineageHudBar: React.FC<MemoryLineageHudBarProps> = ({
  stats,
  isLoading,
  isReorganizing,
  onRefresh,
  onTriggerReorganize,
}) => {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-lg border border-border/70 bg-card/60 backdrop-blur-sm">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-primary/10 text-primary">
            <GitFork className="w-4 h-4" aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Memory Lineage &amp; Reorganization
            </h3>
            <p className="text-sm font-medium text-foreground">
              Evolutionary DAG &amp; Semantic Graph
            </p>
          </div>
        </div>

        <div className="h-6 w-px bg-border/60 hidden sm:block" aria-hidden="true" />

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium">
            <GitCommit className="w-3.5 h-3.5" aria-hidden="true" />
            Active: {stats.active_nodes} / {stats.total_nodes}
          </span>
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 font-medium">
            <Layers className="w-3.5 h-3.5" aria-hidden="true" />
            Superseded: {stats.superseded_nodes}
          </span>
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 font-medium">
            <Network className="w-3.5 h-3.5" aria-hidden="true" />
            Edges: {stats.total_edges}
          </span>
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-purple-500/10 text-purple-600 dark:text-purple-400 font-medium">
            Depth: v{stats.max_depth}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onTriggerReorganize}
          disabled={isReorganizing || isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
          aria-label="Trigger automatic graph reorganization pass"
        >
          <Zap className={`w-3.5 h-3.5 ${isReorganizing ? 'animate-bounce' : ''}`} aria-hidden="true" />
          <span>{isReorganizing ? 'Reorganizing...' : 'Run Reorganizer'}</span>
        </button>

        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          className="p-1.5 rounded-md border border-border/80 bg-background/80 hover:bg-accent text-foreground disabled:opacity-50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
          aria-label="Refresh memory lineage topology"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
};
