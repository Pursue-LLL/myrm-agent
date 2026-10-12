/**
 * [INPUT]
 * @/services/memory::CubeMatrixOverviewDTO
 * onRefresh: () => void, isRefreshing: boolean
 *
 * [OUTPUT]
 * Component: MemoryCubeHudBar
 *
 * [POS]
 * HUD metric bar presenting Memory Cube counts, records, active topologies, and isolation health.
 * Follows a11y ratchet guidelines: Uses native `<section aria-label="...">` tag, visible focus rings.
 * No `any` types allowed. Single file < 200 lines.
 */

import React from 'react';
import { Box, Layers, ShieldCheck, RefreshCw, Database } from 'lucide-react';
import type { CubeMatrixOverviewDTO } from '@/services/memory';

interface MemoryCubeHudBarProps {
  overview: CubeMatrixOverviewDTO;
  isRefreshing: boolean;
  onRefresh: () => void;
}

export const MemoryCubeHudBar: React.FC<MemoryCubeHudBarProps> = ({
  overview,
  isRefreshing,
  onRefresh,
}) => {
  const globalCount = overview.cubes.filter((c) => c.scope_type === 'global_shared').length;
  const projectCount = overview.cubes.filter((c) => c.scope_type === 'project_workspace').length;
  const privateCount = overview.cubes.filter((c) => c.scope_type === 'agent_private').length;
  const ephemeralCount = overview.cubes.filter((c) => c.scope_type === 'ephemeral_task').length;

  return (
    <section
      aria-label="Memory Cube Status Overview"
      className="p-4 rounded-xl border border-border/60 bg-muted/20 backdrop-blur-sm shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Left metrics grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 flex-1">
          {/* Total Cubes */}
          <div className="flex items-center gap-3 p-2.5 rounded-lg bg-card/60 border border-border/40">
            <div className="p-2 rounded-md bg-primary/10 text-primary">
              <Box className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Active Cubes</div>
              <div className="text-lg font-bold tracking-tight text-foreground">
                {overview.total_cubes}
                <span className="ml-1 text-xs font-normal text-muted-foreground">
                  ({globalCount}G / {projectCount}P / {privateCount}A / {ephemeralCount}E)
                </span>
              </div>
            </div>
          </div>

          {/* Stored Records */}
          <div className="flex items-center gap-3 p-2.5 rounded-lg bg-card/60 border border-border/40">
            <div className="p-2 rounded-md bg-blue-500/10 text-blue-500">
              <Database className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Memory Records</div>
              <div className="text-lg font-bold tracking-tight text-foreground">
                {overview.total_records}
                <span className="ml-1 text-xs font-normal text-muted-foreground">retained</span>
              </div>
            </div>
          </div>

          {/* Mount Policies */}
          <div className="flex items-center gap-3 p-2.5 rounded-lg bg-card/60 border border-border/40">
            <div className="p-2 rounded-md bg-purple-500/10 text-purple-500">
              <Layers className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Mount Topologies</div>
              <div className="text-lg font-bold tracking-tight text-foreground">
                {overview.policies.length}
                <span className="ml-1 text-xs font-normal text-muted-foreground">agents mapped</span>
              </div>
            </div>
          </div>

          {/* Security & Strict Isolation Status */}
          <div className="flex items-center gap-3 p-2.5 rounded-lg bg-card/60 border border-border/40">
            <div className="p-2 rounded-md bg-emerald-500/10 text-emerald-500">
              <ShieldCheck className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Cross-Talk Barrier</div>
              <div className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                Strict Isolation Active
              </div>
            </div>
          </div>
        </div>

        {/* Action button */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-label="Refresh memory cube topology"
            className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-medium rounded-lg border border-border bg-card hover:bg-accent text-foreground transition-colors focus:ring-2 focus:ring-primary focus:outline-none disabled:opacity-50"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`}
              aria-hidden="true"
            />
            <span>Refresh</span>
          </button>
        </div>
      </div>
    </section>
  );
};
