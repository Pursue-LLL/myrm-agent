/**
 * [INPUT]
 * @/services/memory::DreamCognitiveOverviewDTO
 * isRefreshing: boolean, onRefresh: () => void
 *
 * [OUTPUT]
 * Component: DreamCognitiveHudBar
 *
 * [POS]
 * HUD metric telemetry bar for Item 125 Dream Cognitive Consolidation & Growth Diary Suite.
 * Follows a11y ratchet guidelines: Uses native `<section aria-label="...">` tag, visible focus rings.
 * No `any` types allowed. Single file < 200 lines.
 */

import React from 'react';
import { BookOpen, Sparkles, Box, Activity, RefreshCw } from 'lucide-react';
import type { DreamCognitiveOverviewDTO } from '@/services/memory';

interface DreamCognitiveHudBarProps {
  overview: DreamCognitiveOverviewDTO;
  isRefreshing: boolean;
  onRefresh: () => void;
}

export const DreamCognitiveHudBar: React.FC<DreamCognitiveHudBarProps> = ({
  overview,
  isRefreshing,
  onRefresh,
}) => {
  return (
    <section
      aria-label="Dream Cognitive Status Overview"
      className="p-4 rounded-xl border border-border/60 bg-muted/20 backdrop-blur-sm shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Left Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 flex-1">
          {/* Total Diaries */}
          <div className="flex items-center gap-3 p-2.5 rounded-lg bg-card/60 border border-border/40">
            <div className="p-2 rounded-md bg-primary/10 text-primary">
              <BookOpen className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Growth Diaries</div>
              <div className="text-lg font-bold tracking-tight text-foreground">
                {overview.total_diaries}
                <span className="ml-1 text-xs font-normal text-muted-foreground">recorded</span>
              </div>
            </div>
          </div>

          {/* Cognitive Mutation Actions */}
          <div className="flex items-center gap-3 p-2.5 rounded-lg bg-card/60 border border-border/40">
            <div className="p-2 rounded-md bg-purple-500/10 text-purple-500">
              <Sparkles className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Cognitive Actions</div>
              <div className="text-lg font-bold tracking-tight text-foreground">
                {overview.total_actions}
                <span className="ml-1 text-xs font-normal text-muted-foreground">mutated</span>
              </div>
            </div>
          </div>

          {/* Associated Memory Cubes */}
          <div className="flex items-center gap-3 p-2.5 rounded-lg bg-card/60 border border-border/40">
            <div className="p-2 rounded-md bg-blue-500/10 text-blue-500">
              <Box className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Active Cubes</div>
              <div className="text-lg font-bold tracking-tight text-foreground">
                {overview.active_cubes.length}
                <span className="ml-1 text-xs font-normal text-muted-foreground">anchored</span>
              </div>
            </div>
          </div>

          {/* Background Dreaming Health */}
          <div className="flex items-center gap-3 p-2.5 rounded-lg bg-card/60 border border-border/40">
            <div className="p-2 rounded-md bg-emerald-500/10 text-emerald-500">
              <Activity className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">Dream Pipeline</div>
              <div className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                Non-Blocking Active
              </div>
            </div>
          </div>
        </div>

        {/* Action Button */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-label="Refresh dream cognitive telemetry"
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
