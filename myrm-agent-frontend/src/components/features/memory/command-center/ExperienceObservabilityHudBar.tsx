/**
 * [INPUT]
 * None
 *
 * [OUTPUT]
 * ExperienceObservabilityHudBar: 4-metric HUD status bar for Item 108 Experience Observability Suite.
 *
 * [POS]
 * Command center status header visualizing tracked experiences, injections, success rates, and host plugin gateway.
 * Single file < 150 lines. Strict typing, zero any.
 */

import React from 'react';
import { Eye, TrendingUp, Cpu, Radio, RefreshCw } from 'lucide-react';

interface ExperienceObservabilityHudBarProps {
  totalTracked: number;
  totalInjections: number;
  overallSuccessRate: number;
  activeChannel: string;
  isPluginEnabled: boolean;
  onRefresh: () => void;
  isRefreshing: boolean;
}

export const ExperienceObservabilityHudBar: React.FC<
  ExperienceObservabilityHudBarProps
> = ({
  totalTracked,
  totalInjections,
  overallSuccessRate,
  activeChannel,
  isPluginEnabled,
  onRefresh,
  isRefreshing,
}) => {
  const successPercent = Math.round(overallSuccessRate * 100);

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 bg-muted/30 rounded-lg border border-border/50">
      {/* 1. Tracked Experiences */}
      <div className="flex items-center gap-2.5 p-2 bg-background/60 rounded border border-border/40">
        <div className="p-1.5 rounded bg-purple-500/10 text-purple-500">
          <Eye className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Tracked Items
          </div>
          <div className="text-sm font-semibold flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full bg-purple-500" />
            {totalTracked} Procedures
          </div>
        </div>
      </div>

      {/* 2. Total Injections */}
      <div className="flex items-center gap-2.5 p-2 bg-background/60 rounded border border-border/40">
        <div className="p-1.5 rounded bg-blue-500/10 text-blue-500">
          <Cpu className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Cumulative Injected
          </div>
          <div className="text-sm font-semibold">
            {totalInjections} Prompt Hooks
          </div>
        </div>
      </div>

      {/* 3. Overall Success Rate */}
      <div className="flex items-center gap-2.5 p-2 bg-background/60 rounded border border-border/40">
        <div className="p-1.5 rounded bg-emerald-500/10 text-emerald-500">
          <TrendingUp className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Attributed Success
          </div>
          <div className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
            {successPercent}% Effective
          </div>
        </div>
      </div>

      {/* 4. Host Gateway Channel */}
      <div className="flex items-center justify-between p-2 bg-background/60 rounded border border-border/40">
        <div className="flex items-center gap-2.5">
          <div
            className={`p-1.5 rounded ${
              isPluginEnabled
                ? 'bg-primary/10 text-primary'
                : 'bg-muted text-muted-foreground'
            }`}
          >
            <Radio className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              Host Channel
            </div>
            <div className="text-sm font-semibold capitalize flex items-center gap-1">
              <span
                className={`inline-block w-2 h-2 rounded-full ${
                  isPluginEnabled ? 'bg-emerald-500' : 'bg-muted-foreground'
                }`}
              />
              {activeChannel}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          aria-label="Refresh observability telemetry"
          className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50 transition-colors"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`}
          />
        </button>
      </div>
    </div>
  );
};
